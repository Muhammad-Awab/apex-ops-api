"""Apex Operations API.

Endpoints
  GET  /healthz                 liveness  - process is up (no dependency checks)
  GET  /readyz                  readiness - DB reachable and schema ready
  GET  /version                 build metadata of the running image
  GET  /metrics                 Prometheus exposition format
  GET  /api/v1/incidents        list incidents
  POST /api/v1/incidents        create incident
  GET  /api/v1/incidents/{id}   fetch one incident

Run with: uvicorn app.main:create_app --factory
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, load_settings
from app.db import Database, Incident
from app.logging_config import configure_logging
from app.metrics import BUILD_INFO, DB_UP, HTTP_LATENCY, HTTP_REQUESTS, INCIDENTS_CREATED

log = logging.getLogger("apex.api")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Probe/scrape endpoints are logged at DEBUG so they don't drown real traffic.
_QUIET_ROUTES = {"/healthz", "/metrics"}


class IncidentIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    severity: Literal["low", "medium", "high", "critical"]


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    severity: str
    status: str
    created_at: datetime


def _short_error(exc: Exception) -> str:
    """One-line, credential-free description of a DB error for logs/responses."""
    detail = getattr(exc, "orig", None) or exc
    return f"{type(detail).__name__}: {str(detail).strip().splitlines()[0][:300]}"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.service_name, settings.app_version, settings.environment)
    db = Database(settings.database_url, settings.db_connect_timeout)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        BUILD_INFO.info(
            {"version": settings.app_version, "git_sha": settings.git_sha, "environment": settings.environment}
        )
        log.info(
            "service starting",
            extra={"event": "startup", "database": settings.database_url_redacted},
        )
        if settings.fault_mode != "none":
            log.warning("fault injection active", extra={"event": "fault_mode", "error": settings.fault_mode})
        try:
            db.ensure_schema()
        except SQLAlchemyError as exc:
            # Stay alive (liveness OK) and let /readyz report not-ready; the
            # schema is retried on the next readiness probe.
            log.error(
                "database unavailable at startup",
                extra={"event": "startup_db_unavailable", "error": _short_error(exc)},
            )
        yield
        db.dispose()
        log.info("service stopped", extra={"event": "shutdown"})

    app = FastAPI(title="Apex Operations API", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    @app.middleware("http")
    async def observe(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "unhandled error",
                extra={"event": "unhandled_exception", "request_id": request_id, "path": request.url.path},
            )
            response = JSONResponse({"detail": "internal server error", "request_id": request_id}, status_code=500)
        elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")  # template, keeps label cardinality bounded
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route_path).observe(elapsed)
        response.headers["X-Request-ID"] = request_id

        level = logging.DEBUG if route_path in _QUIET_ROUTES else logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        log.log(
            level,
            "request",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": route_path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
                "client_ip": request.client.host if request.client else None,
            },
        )
        return response

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"service": settings.service_name, "version": settings.app_version, "docs": "/docs"}

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok"}

    def check_database() -> str | None:
        """Ping the DB and refresh apex_db_up. Returns an error description, or None if healthy."""
        try:
            db.ping()
            db.ensure_schema()
        except SQLAlchemyError as exc:
            DB_UP.set(0)
            return _short_error(exc)
        DB_UP.set(1)
        return None

    @app.get("/readyz", tags=["ops"])
    def readyz() -> JSONResponse:
        if settings.fault_mode == "not_ready":
            return JSONResponse(
                {"status": "not_ready", "checks": {"fault_injection": "FAULT_MODE=not_ready"}}, status_code=503
            )
        error = check_database()
        if error:
            log.warning("readiness check failed", extra={"event": "readiness_failed", "error": error})
            return JSONResponse({"status": "not_ready", "checks": {"database": "unreachable"}}, status_code=503)
        return JSONResponse({"status": "ready", "checks": {"database": "ok"}})

    @app.get("/version", tags=["ops"])
    def version() -> dict:
        return {
            "service": settings.service_name,
            "version": settings.app_version,
            "git_sha": settings.git_sha,
            "environment": settings.environment,
        }

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        # Refresh dependency health on every scrape so apex_db_up is never stale,
        # even when nothing is polling /readyz (e.g. under Docker Compose).
        check_database()
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    def _inject_errors() -> None:
        if settings.fault_mode == "errors":
            raise RuntimeError("injected fault: FAULT_MODE=errors")

    @app.post("/api/v1/incidents", response_model=IncidentOut, status_code=201, tags=["incidents"])
    def create_incident(payload: IncidentIn, request: Request) -> Incident:
        _inject_errors()
        with db.session() as session:
            incident = Incident(title=payload.title, severity=payload.severity)
            session.add(incident)
            session.commit()
            session.refresh(incident)
        INCIDENTS_CREATED.inc()
        log.info(
            "incident created",
            extra={"event": "incident_created", "incident_id": incident.id, "request_id": request.state.request_id},
        )
        return incident

    @app.get("/api/v1/incidents", response_model=list[IncidentOut], tags=["incidents"])
    def list_incidents(limit: int = 50) -> list[Incident]:
        _inject_errors()
        limit = max(1, min(limit, 200))
        with db.session() as session:
            return list(session.scalars(select(Incident).order_by(Incident.id.desc()).limit(limit)))

    @app.get("/api/v1/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
    def get_incident(incident_id: int) -> Incident:
        _inject_errors()
        with db.session() as session:
            incident = session.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident

    return app
