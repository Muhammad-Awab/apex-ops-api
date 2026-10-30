# Apex Operations API: commit-to-release on Docker

A small operations API (FastAPI + PostgreSQL) packaged as a hardened, non-root container. It has a CI pipeline that blocks releases on failed checks, a Docker Compose deployment with health-gated releases, **automatic and manual rollback** through versioned images, structured logs, Prometheus metrics and alerts, and a demonstrated failure investigation.

Everything claimed here is backed by raw logs in [docs/evidence/](docs/evidence/README.md).

## Requirements → where to look

| # | Requirement | Implementation | Evidence |
|---|-------------|----------------|----------|
| 1 | API in Docker, health/readiness, non-root | [app/](app/), [Dockerfile](Dockerfile): `/healthz`, `/readyz`, uid 10001 | [01](docs/evidence/01_ci_local_pass.log), [11](docs/evidence/11_security_posture.log) |
| 2 | CI: deps, lint/tests, build, block on failure | [.github/workflows/ci.yml](.github/workflows/ci.yml), [scripts/ci_local.sh](scripts/ci_local.sh) | [01](docs/evidence/01_ci_local_pass.log), [02](docs/evidence/02_ci_local_intentional_failure.log) |
| 3 | Compose: app + DB, env config, persistence | [docker-compose.yml](docker-compose.yml), [.env.example](.env.example), volume `db_data` | [03](docs/evidence/03_deploy_v1.0.0.log), [07](docs/evidence/07_manual_rollback_and_history.log) |
| 4 | Safe release + rollback, versioned images | [scripts/deploy.sh](scripts/deploy.sh), [scripts/rollback.sh](scripts/rollback.sh) | [05](docs/evidence/05_bad_release_1.2.0_auto_rollback.log), [06](docs/evidence/06_bad_release_1.3.0_smoke_fail_auto_rollback.log), [07](docs/evidence/07_manual_rollback_and_history.log) |
| 5 | Structured logs, health checks, metrics/alerts, failure investigation | [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md), [monitoring/](monitoring/) | [09](docs/evidence/09_incident_drill_db_outage.log), [09a](docs/evidence/09a_incident_drill_finding_slow_readiness.log) |
| 6 | Secrets, least privilege, scanning, cloud cost path | [docs/SECURITY.md](docs/SECURITY.md), [docs/CLOUD_COST_PATH.md](docs/CLOUD_COST_PATH.md) | [01](docs/evidence/01_ci_local_pass.log), [11](docs/evidence/11_security_posture.log) |
| D | ≥6 automated checks incl. one intentional failure | 17 unit tests + intentional failure; 11 CI gates; 8 post-deploy smoke checks | [01](docs/evidence/01_ci_local_pass.log), [02](docs/evidence/02_ci_local_intentional_failure.log) |
| D | Runbook | [docs/RUNBOOK.md](docs/RUNBOOK.md): deploy, rollback, incident response, troubleshooting | |
| D | Diagram, decision memo, AI disclosure | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DECISION_MEMO.md](docs/DECISION_MEMO.md), [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) | |

## Prerequisites
- Docker Engine 24+ with Compose v2 (tested: Docker Desktop 29.1.3, Compose 2.40.3)
- bash and curl (Linux/macOS, or **Git Bash** on Windows)
- Free ports `8080` (API) and `9090` (Prometheus, optional)
- No local Python needed: tests run inside Docker

## Quick start (about 3 minutes)

```bash
# 1. One-time setup: creates .env and a random DB password in secrets/ (both git-ignored)
bash scripts/init_secrets.sh

# 2. Run every CI quality gate locally (lint, tests, audit, hadolint, build, Trivy, compose, promtool)
bash scripts/ci_local.sh

# 3. Build and deploy a versioned release (readiness gate + 8 smoke checks)
bash scripts/build.sh 1.0.0
bash scripts/deploy.sh 1.0.0

# 4. Use it
curl -s http://127.0.0.1:8080/readyz
curl -s -X POST http://127.0.0.1:8080/api/v1/incidents -H 'Content-Type: application/json' \
     -d '{"title":"Disk 90% on node-3","severity":"high"}'
curl -s http://127.0.0.1:8080/api/v1/incidents
# Swagger UI: http://127.0.0.1:8080/docs
```

## Demo script (for the review meeting)

```bash
# Release & upgrade
bash scripts/build.sh 1.1.0 && bash scripts/deploy.sh 1.1.0

# Bad release #1: never becomes ready -> rejected, auto-rollback to 1.1.0
bash scripts/build.sh 1.2.0 --fault not_ready && READY_TIMEOUT=30 bash scripts/deploy.sh 1.2.0

# Bad release #2: healthy but API returns 500 -> smoke tests catch it, auto-rollback
bash scripts/build.sh 1.3.0 --fault errors && bash scripts/deploy.sh 1.3.0

# Manual rollback to the previous good version, then check what is live
bash scripts/rollback.sh && curl -s http://127.0.0.1:8080/version
cat .deploy/history.log

# Failing test blocks the pipeline
bash scripts/ci_local.sh --with-intentional-failure

# Failure investigation: DB outage drill with monitoring and a firing alert
docker compose --profile monitoring up -d prometheus
OUTAGE_SECONDS=100 bash scripts/incident_drill.sh     # alert visible at http://127.0.0.1:9090/alerts
```

Clean up: `docker compose --profile monitoring down` keeps the data. Adding `-v` **deletes the database volume**.

## Running CI on GitHub
1. Push this repository to GitHub. The workflow runs on PRs, pushes to `main` and `v*.*.*` tags.
2. To demonstrate the gate, go to **Actions → CI/CD → Run workflow** and tick `demo_intentional_failure`. The `test` job fails, and `build-scan-integration` and `release` are skipped.
3. Releases: pushing tag `v1.2.3` publishes `ghcr.io/<owner>/apex-ops-api:1.2.3` (plus `:sha-…`). On a host, set `APP_IMAGE=ghcr.io/<owner>/apex-ops-api` in `.env` and run `scripts/deploy.sh 1.2.3`. It pulls the image.
4. Optional: add required reviewers to the `release` environment to get a manual approval gate.

## Automated checks

| Layer | Checks |
|-------|--------|
| Unit tests (17 + 1 intentional) | liveness; readiness OK; readiness 503 + liveness 200 when DB unreachable; readiness 503 under fault; version metadata; create/get/list; 422 on bad input; 404; 500 with request_id and no leak; request-ID generation/propagation/sanitising; metrics with route templates and build info; `apex_db_up` drops when DB down; JSON log format; secret from file + URL-encoding + no leak in repr; fail fast on missing password; invalid fault mode rejected; DSN redaction; **intentional failure** (gated by `RUN_INTENTIONAL_FAILURE=1`) |
| CI gates (11) | ruff lint, ruff format, pytest + coverage ≥80% (currently 98%), pip-audit, hadolint, image build, non-root user, Trivy HIGH/CRITICAL, compose validation, promtool rule check, (GitHub only) Compose integration + bad-release rollback test |
| Post-deploy smoke (8) | `/healthz`, `/readyz`, expected version, create record, read record, metrics, uid 10001, DB port not published |
| Dev-time linters | shellcheck (scripts), actionlint (workflow): both clean |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `APP_VERSION` | (none) | set by deploy/rollback scripts; selects the image tag |
| `APP_IMAGE` | `apex-ops-api` | set to `ghcr.io/<owner>/apex-ops-api` to deploy CI-published images |
| `APP_PORT` | `8080` | bound to 127.0.0.1 only |
| `ENVIRONMENT`, `LOG_LEVEL` | `local`, `INFO` | |
| `DB_USER`, `DB_NAME` | `apex`, `apex_ops` | |
| `DB_PASSWORD_FILE` | `/run/secrets/db_password` | secret file, never an env value |
| `DB_CONNECT_TIMEOUT` | `2` | seconds (libpq minimum 2) |
| `READY_TIMEOUT` | `60` | deploy script: seconds to wait for readiness |

## Assumptions & trade-offs
Summarised in [docs/DECISION_MEMO.md](docs/DECISION_MEMO.md). The most important ones: the target is a single host, so deploys recreate the container and cause **~4–8 s of downtime** (fix proposed). The schema uses `create_all`, not migrations (Alembic with expand/contract is the next step). The GitHub Actions workflow is linted and mirrored locally but needs to be run on GitHub to produce run evidence.

## AI assistance
This submission was built with AI assistance (Claude Code). See [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) for exactly what was AI-generated and how it was verified.
