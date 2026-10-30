# syntax=docker/dockerfile:1
# Multi-stage build:
#   builder  - installs pinned runtime deps into an isolated venv
#   dev      - builder + test/lint tooling + tests (used by CI and scripts/ci_local.sh)
#   runtime  - minimal image: venv + app code, non-root, read-only friendly
# Base pinned by tag + digest for reproducible builds; Dependabot proposes digest bumps.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-virtualenv -r /tmp/requirements.txt

FROM builder AS dev
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --require-virtualenv -r /tmp/requirements-dev.txt
WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests
CMD ["pytest"]

FROM base AS runtime
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
# Only used to build deliberately broken releases for the rollback demo.
ARG FAULT_MODE=none
LABEL org.opencontainers.image.title="apex-ops-api" \
      org.opencontainers.image.description="Apex Operations API" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

# Dedicated unprivileged user; no shell, no home directory.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Code stays owned by root, so the app user can read it but not change it.
COPY app ./app

ENV PATH=/opt/venv/bin:$PATH \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    FAULT_MODE=${FAULT_MODE}

USER 10001:10001
EXPOSE 8080

# Liveness only. Readiness (/readyz, DB-dependent) is checked by the deploy script.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--timeout-graceful-shutdown", "20"]
