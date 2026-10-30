# Security & configuration hygiene

## 1. Secrets handling

| Practice | Implementation |
|----------|----------------|
| No secrets in the repo | `secrets/*` and `.env` are git-ignored, and `.env.example` contains no secrets. The build context excludes `secrets/`, `.env` and `.git` (`.dockerignore`), so secrets cannot end up in image layers |
| Generated, not chosen | `scripts/init_secrets.sh` generates a 32-char random DB password locally and never prints it |
| Delivered as files, not env vars | Docker secrets are mounted at `/run/secrets/db_password`. Postgres uses `POSTGRES_PASSWORD_FILE` and the app uses `DB_PASSWORD_FILE` (`app/config.py: read_secret`). Env vars leak through `docker inspect`, `/proc/*/environ`, crash reports and child processes |
| Never logged | The DSN is only ever logged redacted (`apex:***@db`), and `Settings.__repr__` redacts too. Unit tests check both. Evidence: the secret value appears **0 times** in `docker inspect` or the container logs (`evidence/11_security_posture.log`) |
| Safe encoding | The password is URL-encoded into the DSN, so special characters cannot break or inject into it (unit test) |
| Fail fast | A missing secret raises a clear `ConfigError` at startup instead of falling back to a default password |
| CI | No long-lived credentials. Publishing uses the short-lived, job-scoped `GITHUB_TOKEN`. The integration job generates a throwaway secret per run |
| Cloud path | Replace the file with a managed secret store (AWS Secrets Manager / GCP Secret Manager / Azure Key Vault), injected as a file or env var by the platform and read through workload identity (no static keys). Rotation: create a new DB user/password, roll the app, then drop the old one |

**Known local limitation:** on Windows/NTFS the `chmod 700/644` in `init_secrets.sh` has no effect (see the evidence). On Linux/macOS hosts the directory is owner-only.

## 2. Least privilege

**Container (verified in `evidence/11_security_posture.log`)**
- Runs as a dedicated uid/gid **10001** with a `nologin` shell and no home directory (`USER` in the Dockerfile and `user:` in Compose). CI fails the build if the image user is not `10001:10001`.
- **Read-only root filesystem.** The only writable path is a 16 MB `tmpfs` at `/tmp`. App code is owned by root, so the app user cannot modify it (a write to `/app` returns `EROFS`).
- `cap_drop: [ALL]`, `no-new-privileges:true`, not privileged.
- CPU and memory limits on every service, which contains runaway or DoS impact. Log rotation prevents disk exhaustion.

**Network**
- The DB has **no published port** and sits on an `internal: true` network with no egress and no host exposure. A smoke check verifies it.
- The API binds to `127.0.0.1` only. A reverse proxy or LB with TLS would front it in any shared environment.

**Database**
- The app uses a dedicated non-superuser role in the target design. Locally the bootstrap user `apex` owns its own database only. Next step: separate `migrator` (DDL) and `app` (DML only) roles.

**CI/CD**
- Workflow default `permissions: contents: read`. Only the `release` job gets `packages: write`, and only on `main` or tags (never on PRs from forks).
- The `release` job uses a GitHub **environment**, so required reviewers can be added as a manual approval gate.
- Concurrency group per ref: no racing deploys. Locally, `deploy.sh` uses a lock directory.

## 3. Dependency & image scanning

| Layer | Tool | Gate |
|-------|------|------|
| Python dependencies | `pip-audit --strict` (PyPI advisory DB / OSV) | any known vulnerability fails CI |
| OS packages in the image | Trivy `--severity HIGH,CRITICAL --ignore-unfixed` | exit code 1 fails CI |
| Dockerfile | hadolint, `--failure-threshold warning` | fails CI (it caught an unpinned base image) |
| Code | ruff with the `S` rules (flake8-bandit security checks) | fails CI |
| Workflow / scripts | actionlint, shellcheck | run during development (results in the README) |
| Ongoing | Dependabot (pip, docker, github-actions), weekly | update PRs go through the same gates |

**Supply chain**
- All Python dependencies are **pinned, including transitive ones** (`requirements.txt`). The base image is pinned by **tag and digest**. Tool images are pinned by version (`hadolint:v2.12.0`, `trivy:0.58.1`, `prometheus:v2.55.1`).
- **Build once, promote:** the exact image that passed the scan and integration tests is exported and pushed. It is never rebuilt for release.
- Image tags are **immutable**. Both `build.sh` and the release job refuse to overwrite an existing version, and no `latest` tag is published.
- Accepted risk: `--ignore-unfixed` hides CVEs that have no fix yet. Review them periodically with `trivy image apex-ops-api:<v>` without that flag.
- Next steps: pin GitHub Actions by commit SHA, sign images with cosign (keyless OIDC), attach an SBOM and provenance attestation, and verify signatures at deploy time.

## 4. Application-level
- Input validation through Pydantic (`severity` enum, title length), with a unit test.
- 500 responses never include exception details, only a `request_id` (unit test).
- `X-Request-ID` is accepted only if it matches `[A-Za-z0-9._-]{1,64}`, which prevents header and log injection (unit test).
- Not in scope, and needed before real exposure: authentication/authorization (OIDC/JWT), TLS, rate limiting, CORS policy.
