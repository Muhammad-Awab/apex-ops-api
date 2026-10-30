# Decision memo: Apex Operations API delivery pipeline

**Goal:** a reproducible local environment and a reliable, evidenced path from commit to release, including safe rollback, for a small operations API.

## Assumptions
- "Minimal API" means a small CRUD service with a real database. The domain (operational incidents) is invented, and all data is synthetic.
- The target is a single host running Docker Compose. No paid cloud and no production systems, as the brief requires.
- CI runs on GitHub Actions (free for public repos, and the most common choice). The "deployment" in CI is a full Compose deploy on the runner plus publishing to GHCR. Deploying to a real host is a manual `deploy.sh <version>` run, because there is no reachable target environment.
- Reviewers have Docker and bash (Linux/macOS, or Git Bash on Windows). No local Python is needed.

## Key decisions

| Decision | Why | Trade-off accepted |
|----------|-----|--------------------|
| **Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL** | Small and readable, mature ecosystem, Prometheus client available. Postgres is a realistic dependency, unlike a mock | Heavier image (~180 MB) than Go. Acceptable at this scale |
| **Unit tests on SQLite, integration on real Postgres** | Unit tests run in ~1.5 s with no Docker needed. Postgres behaviour is still exercised by the Compose smoke tests in CI | Small dialect differences could slip past unit tests. The integration stage covers that |
| **Liveness ≠ readiness** | Restarting the app does not fix a DB outage. Readiness gates traffic and deploys | Two endpoints to keep correct (both tested) |
| **Docker secrets (files), not env vars** | Env vars leak via `inspect`, `/proc` and crash dumps. The same file contract maps directly to cloud secret managers | One extra setup step (`init_secrets.sh`) |
| **Release = immutable semver image + gated `deploy.sh`** | Rollback becomes "run a known image again", which is fast and deterministic. Every release passes readiness and smoke gates | No `latest` tag, so you must name a version (intentional) |
| **Automatic rollback on failed gates** | Restores the last known-good version without human reaction time (~15 s in evidence 05 and 06) | Two bad releases in a row roll back to the last *good* version, not the previous attempt. That is intended |
| **Recreate strategy (single app container)** | Simple and transparent for a single host | **~4–8 s of downtime per deploy.** Fix: two app replicas behind Caddy/Traefik for blue/green, or platform revisions in the cloud (see CLOUD_COST_PATH) |
| **"Build once, promote"** in CI | The bits published are exactly the bits that were scanned and tested | Uses an artifact upload (~60 MB) between jobs |
| **Fault-injection flag (`FAULT_MODE`) baked into "bad" images** | Makes failed-release and rollback demos reproducible on any machine | Test-only code path in production code. It is off by default, validated, and logged loudly when on. In a real product I'd keep this in a test harness instead |
| **Schema via `create_all`** instead of Alembic | Scope: the schema is identical across all demo versions | Not acceptable for real releases. Next step is Alembic with expand/contract migrations (Runbook §2) |
| **Bash scripts instead of Ansible/Make/Helm** | Zero extra tooling, readable during a review, and the same scripts run locally and in CI | Bash is less portable. Shellcheck-clean and kept small to compensate |

## What the evidence shows
11 quality gates pass, and the intentional failure blocks the release. Two different kinds of bad release were caught and auto-rolled back. A manual rollback and roll-forward worked. A DB outage drill fired a real alert, liveness and readiness behaved correctly, and no data was lost. See `docs/evidence/README.md`. Two genuine defects came out of running the system rather than just writing it: the stale `apex_db_up` gauge and readiness slower than the probe timeout. Both were root-caused, fixed and re-verified. The second one disproved my first hypothesis (see OBSERVABILITY.md §5).

## Risks / known gaps
- GitHub Actions has not yet been run on GitHub (validated with actionlint, mirrored locally). This is the first thing to do after pushing.
- No auth/TLS/rate limiting. Fine for local-only, required before any exposure.
- Single DB with no automated backups locally (manual `pg_dump` in the runbook).
- GitHub Actions are pinned by major tag, not by SHA.

## With more time (priority order)
1. Run the pipeline on GitHub and attach the run evidence. Add a branch-protection rule that requires the `CI/CD` checks to pass.
2. Alembic migrations with an expand/contract policy, plus a migration step in `deploy.sh`.
3. Zero-downtime blue/green on Compose (2 replicas + Caddy) or move to Cloud Run revisions.
4. Image signing (cosign) + SBOM + verifying signatures at deploy time. Pin Actions by SHA.
5. Readiness with its own overall deadline / cached result (follow-up from the drill).
6. Alertmanager + Grafana dashboard. SLO burn-rate alerts instead of static thresholds.
7. OpenTelemetry traces (`request_id` → `trace_id`).
