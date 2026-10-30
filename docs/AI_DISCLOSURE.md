# AI-use disclosure

> **Candidate: review and edit this file before submitting.** It must describe *your* process accurately. Replace every `[CANDIDATE: …]` marker. The reviewers will ask you to explain and change any part of this submission live, so make sure you can.

## Tool used
- **Claude Code** (Anthropic; model: Claude Opus 5.5), used as an agent inside VS Code on the candidate's machine. It could read and write files in this folder and run shell commands (Docker, bash).

## What the AI did
| Area | AI contribution |
|------|-----------------|
| Application (`app/`) | Wrote the FastAPI service: config/secret loading, JSON logging, metrics, health/readiness, CRUD endpoints, fault-injection flag |
| Tests (`tests/`) | Wrote the 17 unit tests and the intentional-failure test |
| Containers | Wrote the Dockerfile, `.dockerignore` and `docker-compose.yml` (hardening, secrets, networks, limits) |
| CI/CD | Wrote `.github/workflows/ci.yml` and `dependabot.yml` |
| Scripts | Wrote build, deploy, rollback, smoke test, local CI, incident drill and secret init |
| Monitoring | Wrote the Prometheus config and alert rules |
| Execution & evidence | Ran every command that produced `docs/evidence/*.log`. The logs are raw tool output, not written by the AI |
| Debugging | Diagnosed the issues found during execution: Git Bash path conversion, a SIGPIPE in secret generation, the `compose port` smoke-test bug, the stale `apex_db_up` gauge, and the slow-DNS readiness issue (including a first hypothesis that turned out wrong) |
| Documentation | Drafted all of `docs/` and `README.md` |
| Dependency versions | Resolved by running `pip install` in `python:3.12-slim` and freezing the result (not chosen from memory), then audited with pip-audit |

## What the candidate did
- [CANDIDATE: e.g. defined scope and requirements, chose the stack, reviewed every file, changed X/Y, re-ran the scripts yourself, pushed to GitHub and captured the Actions screenshots, …]
- [CANDIDATE: list anything you rewrote or decided differently from the AI's suggestions]

## How correctness was checked
- Nothing is claimed without a matching log in `docs/evidence/`. Failures found along the way are kept as evidence (`03a_*`, `09a_*`) and not hidden.
- Linters: ruff, hadolint, shellcheck, actionlint, promtool. Scanners: pip-audit, Trivy.
- [CANDIDATE: describe your own verification, e.g. "I ran `scripts/ci_local.sh` and the deploy/rollback demo on my machine on <date>"]

## Data
Only synthetic data was used (incident titles like "smoke test incident"). No real customer data, no Apex systems, no real credentials. The DB password is generated locally and is not part of the submission.
