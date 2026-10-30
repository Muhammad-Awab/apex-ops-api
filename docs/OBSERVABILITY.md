# Observability

## 1. Structured logs

The app writes one JSON object per line to stdout, and Docker's `json-file` driver rotates the files (10 MB × 3). Example from a real run:

```json
{"ts": "2026-10-30T06:45:11.857+00:00", "level": "WARNING", "logger": "apex.api", "msg": "readiness check failed",
 "service": "apex-ops-api", "version": "1.4.0", "env": "local", "event": "readiness_failed",
 "error": "OperationalError: failed to resolve host 'db': [Errno -2] Name or service not known"}
```

| Field | Purpose |
|-------|---------|
| `ts`, `level`, `logger`, `msg` | standard |
| `service`, `version`, `env` | on every line, so you can tell which release logged an error (key during rollback decisions) |
| `event` | stable machine-readable name: `http_request`, `readiness_failed`, `unhandled_exception`, `incident_created`, `startup`, `startup_db_unavailable`, `fault_mode`, `shutdown` |
| `request_id` | taken from `X-Request-ID` if it is safe (`[A-Za-z0-9._-]{1,64}`), otherwise generated. Echoed in the response header and in 500 bodies, so a user report can be traced to log lines |
| `method`, `path`, `route`, `status`, `duration_ms`, `client_ip` | access log, written by middleware (uvicorn's access log is disabled to avoid duplicates) |
| `exc_type`, `stack` | on unhandled exceptions. The stack trace goes to logs only; clients get a generic 500 with the `request_id` |

Rules: no secrets in logs (the DSN is logged redacted as `postgresql+psycopg://apex:***@db…`, which is verified in `docs/evidence/11_security_posture.log`). Probe and scrape requests (`/healthz`, `/metrics`) log at DEBUG to keep noise down, and 5xx log at ERROR.

Useful queries (local):
```bash
docker compose logs --no-log-prefix app | grep '"event": "unhandled_exception"'
docker compose logs --no-log-prefix app | grep '"request_id": "<id from user>"'
docker compose logs --no-log-prefix app | grep '"status": 5'
```

## 2. Health checks

| Endpoint | Meaning | Checks | Used by |
|----------|---------|--------|---------|
| `GET /healthz` | **liveness**: the process can serve HTTP | nothing external | Docker `HEALTHCHECK` (restart policy), k8s livenessProbe |
| `GET /readyz` | **readiness**: safe to send traffic | DB `SELECT 1` + schema present | `deploy.sh` and `rollback.sh` gates, load balancer / k8s readinessProbe |

Liveness deliberately ignores the database. If the DB is down, restarting the app does not help, and a liveness check that included the DB would cause restart storms. The drill shows this: during the outage `/healthz` stays 200 and the container stays `healthy`, while `/readyz` returns 503.

## 3. Metrics (Prometheus, `GET /metrics`)

| Metric | Type | Labels | Use |
|--------|------|--------|-----|
| `apex_http_requests_total` | counter | method, route, status | traffic and error rate (RED) |
| `apex_http_request_duration_seconds` | histogram | method, route | latency percentiles |
| `apex_db_up` | gauge | none | dependency health, refreshed on every scrape and every `/readyz` |
| `apex_incidents_created_total` | counter | none | business throughput |
| `apex_build_info` | info | version, git_sha, environment | correlate changes in error rate with a release |

`route` is the route **template** (`/api/v1/incidents/{incident_id}`), not the raw path. This keeps label cardinality bounded and is covered by a unit test.

Local Prometheus: `docker compose --profile monitoring up -d prometheus`, then open http://localhost:9090 (Targets, Alerts).

## 4. Alert proposal

Rules live in `monitoring/alert_rules.yml`, are validated with `promtool` in CI, and are loaded by the local Prometheus. Each rule links to a runbook section.

| Alert | Condition | For | Severity | Why this threshold |
|-------|-----------|-----|----------|--------------------|
| `ApexApiDown` | `up == 0` | 1m | page | the service cannot be reached at all |
| `ApexDatabaseUnreachable` | `apex_db_up == 0` | 1m | page | every write fails. 1m avoids paging on a DB restart blip |
| `ApexHighErrorRate` | 5xx / all > 5% | 5m | page | user-visible failures. 5m window avoids flapping |
| `ApexHighLatencyP95` | p95 > 500 ms (excl. probes) | 10m | ticket | degradation, not an outage, so it goes to working hours |

Proposed SLO for a production version: 99.5% of non-probe requests succeed (non-5xx) over 30 days, with p95 < 300 ms. The next step would be to replace the static thresholds with multi-window burn-rate alerts on that SLO.

Routing (not deployed locally): Alertmanager sends `page` to on-call (PagerDuty/Opsgenie) and `ticket` to a team channel. Alerts are grouped by `alertname` and inhibited while `ApexApiDown` fires.

## 5. Failure investigation (demonstrated)

**Scenario:** the database becomes unavailable (`scripts/incident_drill.sh` stops the `db` container).

**Detect.** `ApexDatabaseUnreachable` went to *firing* in Prometheus. `/readyz` returned 503 and `apex_db_up` was 0.

**Triage.** `docker compose ps` showed `db exited` and `app running (healthy)`, so the app was alive but its dependency was down.

**Diagnose.** The `readiness_failed` log event gave the exact cause: `failed to resolve host 'db'` (the container is gone, so its DNS name is gone too).

**Remediate.** `docker compose start db`. Readiness recovered without restarting the app (the connection pool uses `pool_pre_ping`).

**Verify.** `/readyz` returned 200, `apex_db_up` returned to 1, and a record written before the outage was still present (named volume).

### Finding from the drill (mini post-incident review)

| | |
|---|---|
| **What happened** | In the first run (`evidence/09a_*`) `/readyz` took **3.8 s** to return 503. The probe's 3 s timeout expired first, so monitoring saw "no response" instead of a clear "not ready". |
| **First hypothesis (wrong)** | libpq `connect_timeout=3`. I lowered it to 2 s (v1.5.0), re-ran the drill and still saw 3.85 s, so I rejected the hypothesis. |
| **Root cause** | I measured inside the container: `getaddrinfo('db')` takes ~4 s to fail once the `db` container is gone, through Docker's embedded DNS. Name resolution happens before, and outside, libpq's connect timeout. |
| **Fix** | `dns_opt: [timeout:1, attempts:1]` on the app service. The re-measured lookup failed in 1.03 s, `/readyz` answered 503 in ~1.0 s, and the full drill was re-run green (`evidence/09_*`). |
| **Lessons / follow-ups** | (1) Every dependency check behind a probe needs a bounded total time, below the probe timeout. (2) Verify a fix by re-running the experiment, not by reasoning about it. (3) Follow-up: give readiness its own overall deadline (for example, cache the last result for 2 s) so the bound does not depend on resolver behaviour per platform. |

A second, pre-existing gap was found while preparing the drill: `apex_db_up` was only updated when someone called `/readyz`, and nothing does that under Compose, so Prometheus would have seen a stale `1` during an outage. v1.4.0 refreshes the gauge on every scrape, and a regression test was added.
