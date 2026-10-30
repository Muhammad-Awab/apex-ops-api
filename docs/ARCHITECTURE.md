# Architecture

## Runtime (local, Docker Compose)

```mermaid
flowchart LR
    user([Operator / client]) -- "HTTP 127.0.0.1:8080" --> app

    subgraph host["Docker host"]
      subgraph frontend["network: frontend"]
        app["app<br/>apex-ops-api:&lt;semver&gt;<br/>FastAPI + uvicorn<br/>uid 10001, read-only FS,<br/>cap_drop ALL"]
        prom["prometheus (profile: monitoring)<br/>127.0.0.1:9090<br/>alert_rules.yml"]
      end
      subgraph backend["network: backend (internal, no egress)"]
        db[("db<br/>postgres:16-alpine<br/>no published port")]
      end
      vol[("volume: db_data")]
      sec[/"secret: db_password<br/>/run/secrets/db_password"/]
    end

    app -- "SQL (psycopg)" --> db
    db --- vol
    sec -.-> app
    sec -.-> db
    prom -- "scrape /metrics 15s" --> app
    app -- "JSON logs (stdout)" --> logs[(docker json-file<br/>10MB x 3)]
```

- **app**: the Apex Operations API. `/healthz` and `/readyz` probes, `/metrics`, `/version`, and `/api/v1/incidents` CRUD (create, list, get).
- **db**: PostgreSQL 16. Data lives on the named volume `db_data` and survives container recreation (shown in evidence 07 and 09).
- **prometheus**: optional. Scrapes the app and evaluates four alert rules.

## Commit-to-release pipeline

```mermaid
flowchart LR
    commit([git push / PR / tag]) --> test
    commit --> hadolint

    subgraph ci["GitHub Actions: .github/workflows/ci.yml"]
      test["test<br/>ruff lint + format<br/>pytest + coverage ≥80%<br/>pip-audit"]
      hadolint["dockerfile-lint<br/>hadolint"]
      bsi["build-scan-integration<br/>build versioned image<br/>non-root check<br/>Trivy HIGH/CRITICAL<br/>compose + promtool validate<br/>deploy.sh + 8 smoke checks<br/>bad release → auto-rollback test"]
      rel["release (main/tags only)<br/>environment: release (approval)<br/>push SAME tested image<br/>ghcr.io/…:semver, :sha-xxxxxxx"]
    end

    test --> bsi
    hadolint --> bsi
    bsi --> rel
    rel --> reg[(GHCR)]
    reg -- "scripts/deploy.sh &lt;semver&gt;" --> env["Target host<br/>(local Compose)"]

    fail{{"any check fails"}} -. "downstream jobs skipped<br/>nothing published" .-> rel
```

`scripts/ci_local.sh` runs the same gates locally in Docker, so a contributor can reproduce CI without GitHub.

## Release / rollback flow (`scripts/deploy.sh`)

```mermaid
flowchart TD
    A[deploy.sh VERSION] --> B{preflight + lock<br/>image exists or pullable?}
    B -- no --> X[abort, nothing changed]
    B -- yes --> C[APP_VERSION=VERSION in .env<br/>db healthy → recreate app]
    C --> D{"/readyz 200<br/>within READY_TIMEOUT?"}
    D -- yes --> E{"smoke_test.sh<br/>8/8 pass?"}
    D -- no --> F
    E -- yes --> G[record success<br/>VERSION = new last-known-good]
    E -- no --> F[record failed<br/>dump last 20 log lines]
    F --> H{last known-good exists?}
    H -- yes --> I[rollback.sh LAST_GOOD<br/>same gates] --> J[exit 1: release rejected,<br/>service restored]
    H -- no --> K[exit 1: leave for investigation]
```

## Repository layout

```
app/                 FastAPI service (config, db, logging, metrics, main)
tests/               17 unit tests + 1 intentional failure (pytest, SQLite)
Dockerfile           multi-stage: builder → dev (tests) → runtime (non-root)
docker-compose.yml   app + postgres (+ prometheus profile), secrets, volumes, networks
.github/workflows/   CI/CD pipeline;  .github/dependabot.yml
monitoring/          prometheus.yml, alert_rules.yml
scripts/             build, deploy, rollback, smoke_test, ci_local, incident_drill, init_secrets
docs/                runbook, decision memo, security, observability, cloud path, AI disclosure, evidence/
```
