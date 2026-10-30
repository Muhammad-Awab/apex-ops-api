# Runbook: Apex Operations API

All commands run from the repository root in a bash shell (Linux/macOS, or Git Bash on Windows).

| Item | Value |
|------|-------|
| Service URL | http://127.0.0.1:8080 (`/docs` for the API, `/version` for the running release) |
| Health | `/healthz` (liveness), `/readyz` (readiness) |
| Metrics / alerts | `/metrics`; Prometheus at http://127.0.0.1:9090 (`--profile monitoring`) |
| Release state | `APP_VERSION` in `.env` (what Compose runs); `.deploy/history.log` (audit trail) |
| Images | `apex-ops-api:<semver>` locally; `ghcr.io/<owner>/apex-ops-api:<semver>` from CI |

---

## 1. Deploy

**Pre-checks:** CI is green for the commit, the version is new (tags are immutable), and nobody else is deploying (the script holds a lock).

```bash
bash scripts/build.sh 1.6.0          # or publish via CI and set APP_IMAGE=ghcr.io/<owner>/apex-ops-api in .env
bash scripts/deploy.sh 1.6.0
```

What `deploy.sh` does:
1. Preflight: `.env` and secret present, Docker reachable, deploy lock acquired. Pulls the image if it is not local.
2. Sets `APP_VERSION` in `.env`, makes sure `db` is healthy, recreates `app` on the new image.
3. **Gate 1:** `/readyz` must return 200 within `READY_TIMEOUT` (default 60 s).
4. **Gate 2:** `smoke_test.sh` runs 8 checks: health, readiness, correct version, create+read a record, metrics, uid 10001, DB not exposed.
5. On success it records `deploy <v> success`. On failure it prints the last 20 app log lines, records `failed`, **automatically rolls back to the last known-good version**, and exits 1.

**Post-checks (5 min):** watch `/metrics` and Prometheus for error rate and latency, and `docker compose logs -f app | grep '"level": "ERROR"'`.

**Known trade-off:** the single app container is recreated, so expect ~4–8 s of unavailability per deploy (see the "readiness OK after Ns" lines in the evidence). For zero-downtime, see `DECISION_MEMO.md`.

## 2. Rollback

Use it when a release is unhealthy, error rate or latency regressed after a deploy, or a bad change was discovered later.

```bash
bash scripts/rollback.sh            # back to the previous known-good version (from .deploy/history.log)
bash scripts/rollback.sh 1.4.0      # or an explicit version
curl -s 127.0.0.1:8080/version      # confirm
```

It runs the same readiness and smoke gates as a deploy. Typical duration: **10–20 s** (see `evidence/05`, `06`, `07`).

**Manual fallback** (if the scripts themselves are broken):
```bash
sed -i 's/^APP_VERSION=.*/APP_VERSION=1.4.0/' .env
docker compose up -d --no-deps --force-recreate app
curl -s 127.0.0.1:8080/readyz && curl -s 127.0.0.1:8080/version
```

**Database caveat:** rolling back the image does **not** roll back data. Releases must keep the schema backward compatible (expand/contract): add columns or tables in release N, and remove old ones only in N+2. Never pair a destructive migration with a code change in the same release. If data is corrupted, restore from backup (see 4.4) instead of rolling back.

## 3. Incident response

| Severity | Definition | Response |
|----------|------------|----------|
| SEV1 | API down or every write failing (`ApexApiDown`, `ApexDatabaseUnreachable`) | page on-call, start an incident channel, updates every 30 min |
| SEV2 | partial errors >5% or a single feature broken (`ApexHighErrorRate`) | page on-call, updates every 60 min |
| SEV3 | degraded latency, no errors (`ApexHighLatencyP95`) | ticket, fix within business hours |

**Steps:**
1. **Acknowledge** the alert and name an incident lead. Write down the start time.
2. **Assess impact** with `curl -s :8080/readyz`, `docker compose ps`, and the error rate in Prometheus.
3. **Recent change?** Check `tail .deploy/history.log`. If a deploy happened shortly before symptoms started, **roll back first and investigate after.** That is the fastest mitigation.
4. **Mitigate** using the matching scenario in section 4.
5. **Verify** recovery: `/readyz` 200, smoke tests pass (`bash scripts/smoke_test.sh`), alert resolved.
6. **Communicate**: impact, timeline, current status, next update time.
7. **Post-incident review** within 2 working days: blameless, with timeline, root cause, and action items with owners. Example: `OBSERVABILITY.md` §5.

Rehearse with `bash scripts/incident_drill.sh` (simulated DB outage).

## 4. Troubleshooting

### Scenario A: API down / not responding
```bash
docker compose ps                                   # app running? restarting? health status?
docker compose logs --no-log-prefix --tail 100 app  # look for startup errors / tracebacks
curl -sv 127.0.0.1:8080/healthz
```
| Symptom | Likely cause | Action |
|---------|--------------|--------|
| app `Restarting`, log says `database password missing` / `cannot read secret file` | secret file missing or unreadable | `bash scripts/init_secrets.sh`; check that `secrets/db_password.txt` exists and is readable (mode 644) |
| `APP_VERSION is not set` | `.env` missing or damaged | `cp .env.example .env`, then deploy a known version |
| `port is already allocated` | another process on 8080 | change `APP_PORT` in `.env`, or stop the other process |
| container `unhealthy` with no errors | out of memory (limit 256M) | `docker inspect -f '{{.State.OOMKilled}}' $(docker compose ps -q app)` |
| started right after a deploy | bad release | `bash scripts/rollback.sh` |

### Scenario B: Readiness failing / database unreachable
```bash
curl -s 127.0.0.1:8080/readyz
docker compose ps db
docker compose logs --no-log-prefix --since 10m app | grep readiness_failed   # exact error text
docker compose logs --tail 50 db
```
| Error in `readiness_failed` | Cause | Action |
|-----------------------------|-------|--------|
| `failed to resolve host 'db'` | db container stopped or removed | `docker compose up -d --wait db` |
| `password authentication failed` | secret changed after the volume was initialised (Postgres keeps the original password) | put the original secret back, or rotate inside Postgres: `ALTER USER apex PASSWORD ...` and then update the file |
| `connection refused` / timeout | db starting or overloaded | wait for `pg_isready`; check `docker stats` |
| `could not extend file` / `No space left` | disk full | free disk space; check volume size with `docker system df -v` |

### Scenario C: Elevated 5xx after a release
1. Check whether the errors match a release: compare `apex_build_info{version=...}` with the error-rate graph, and look at the `version` field in error logs.
2. If yes, **roll back** (`bash scripts/rollback.sh`), then investigate on the side.
3. Investigate: `docker compose logs --no-log-prefix app | grep '"event": "unhandled_exception"'`. The `stack` field holds the traceback, and `request_id` ties it to the client report.

### Scenario D: Slow responses
```bash
curl -s 127.0.0.1:8080/metrics | grep apex_http_request_duration_seconds_bucket
docker stats --no-stream                  # CPU throttling at the 0.5 CPU limit? memory near 256M?
docker compose exec db psql -U apex -d apex_ops -c "select pid, state, now()-query_start as age, left(query,60) from pg_stat_activity where state <> 'idle';"
```
Typical causes are CPU limits, slow DB queries, or the DB under load. Short term: raise the limits in `docker-compose.yml`. Long term: profile, add indexes.

### 4.4 Backup & restore (data)
```bash
docker compose exec -T db pg_dump -U apex -d apex_ops -Fc > backup_$(date +%F).dump
docker compose exec -T db pg_restore -U apex -d apex_ops --clean < backup_YYYY-MM-DD.dump
```
`docker compose down -v` **deletes the database volume**. Never use `-v` outside throwaway or CI environments.

### Useful commands
```bash
docker compose ps
docker compose logs -f --no-log-prefix app
tail -20 .deploy/history.log
docker images apex-ops-api
rm -rf .deploy/lock          # only if a deploy crashed and left the lock behind
docker compose down          # stop everything, keep data
```
