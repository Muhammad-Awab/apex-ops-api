"""Structured (JSON, one object per line) logging.

JSON lines can be shipped as-is to Loki, CloudWatch, Elasticsearch, etc. and
queried by field (e.g. ``request_id``, ``status``) during an investigation.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

# Fields that callers may attach via ``logger.info(..., extra={...})``.
EXTRA_FIELDS = (
    "request_id",
    "method",
    "path",
    "route",
    "status",
    "duration_ms",
    "client_ip",
    "event",
    "error",
    "incident_id",
    "database",
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str, environment: str) -> None:
        super().__init__()
        self._static = {"service": service, "version": version, "env": environment}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **self._static,
        }
        for field in EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, service: str, version: str, environment: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, version, environment))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # Route uvicorn's own loggers through the same JSON handler.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # Access logging is done by our middleware (with request_id + latency).
    logging.getLogger("uvicorn.access").disabled = True
