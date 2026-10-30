# AI-use disclosure

## Tool used
- **Claude Code** (Anthropic; model: Claude Opus 5.5), used as an agent inside VS Code on my machine. It could read and write files in this folder and run shell commands (Docker, bash).

## How I used it
I used the AI agent as a pair-engineer to speed up implementation. I set the direction, ran the delivery on GitHub, debugged the CI failure, and own the decisions documented in `DECISION_MEMO.md`.

## How I worked with the AI
I treated the AI as a capable engineer who needs good context, not a magic box:
- **Gave it the source of truth, not a summary.** I supplied the full assessment brief and framed the role and goal (deliver the complete assessment to a senior DevOps standard), so the output was scoped to the rubric rather than a generic demo.
- **Asked for a plan before acting.** Before touching GitHub I had it give me an ordered, step-by-step execution plan (repo → push → CI evidence → intentional-failure run → disclosure → review). Then I worked through it.
- **Challenged its decisions.** I questioned choices instead of accepting them, for example whether the test suite should be pushed at all, and what the assessment's rules on AI use actually are.
- **Reported failures with full context.** When the first GitHub Actions run failed, I didn't say "CI is broken". I shared the failing job, the failing step, and the surrounding log lines (`smoke_test.sh: Permission denied`, the deploy gate's output). With that context the root cause (executable bit lost on Windows) was found and fixed in one iteration, without guesswork.
- **Kept ownership of what is true.** Statements about my own work are limited to what I actually did, and every technical claim is backed by evidence in `docs/evidence/`.

## What the AI did
| Area | AI contribution |
|------|-----------------|
| Application (`app/`) | Wrote the FastAPI service: config/secret loading, JSON logging, metrics, health/readiness, CRUD endpoints, fault-injection flag |
| Tests (`tests/`) | Wrote the 17 unit tests and the intentional-failure test |
| Containers | Wrote the Dockerfile, `.dockerignore` and `docker-compose.yml` (hardening, secrets, networks, limits) |
| CI/CD | Wrote `.github/workflows/ci.yml` and `dependabot.yml` |
| Scripts | Wrote build, deploy, rollback, smoke test, local CI, incident drill and secret init |
| Monitoring | Wrote the Prometheus config and alert rules |
| Local execution & evidence | Ran the commands that produced `docs/evidence/*.log` on my machine. The logs are raw tool output, not written by the AI |
| Debugging (local) | Diagnosed issues found while running locally: Git Bash path conversion, a SIGPIPE in secret generation, the `compose port` smoke-test bug, the stale `apex_db_up` gauge, and the slow-DNS readiness issue (including a first hypothesis that turned out wrong) |
| Documentation | Drafted all of `docs/` and `README.md` |
| Dependency versions | Resolved by running `pip install` in `python:3.12-slim` and freezing the result (not chosen from memory), then audited with pip-audit |

## What I did
- Provided the assessment brief, defined the goal (a complete, evidence-backed submission), and directed the work.
- Created the GitHub repository, committed under my own identity, and pushed.
- Ran the pipeline on GitHub Actions. **The first run failed** in the integration job with `scripts/smoke_test.sh: Permission denied`. I traced it from the Actions log: the executable bit is lost when committing from Windows, so a script calling another script directly fails on the Linux runner. The deploy gate correctly refused to mark the release good. The fix (call helper scripts through `bash`, plus `git update-index --chmod=+x`) was applied and pushed, and I re-ran the pipeline.
- Ran the `demo_intentional_failure` workflow to show that a failing test skips the build, scan and release jobs on GitHub.
- Captured the GitHub Actions evidence (screenshots in `docs/evidence/`).
- Reviewed the submission and prepared to demo, explain and modify it in the live review.

## How correctness was checked
- Nothing is claimed without a matching log or screenshot in `docs/evidence/`. Failures found along the way are kept as evidence (`03a_*`, `09a_*`, and the first failed GitHub run) and not hidden.
- Linters: ruff, hadolint, shellcheck, actionlint, promtool. Scanners: pip-audit, Trivy.
- The pipeline was run on GitHub Actions on my repository, in addition to the local runs.

## Data
Only synthetic data was used (incident titles like "smoke test incident"). No real customer data, no Apex systems, no real credentials. The DB password is generated locally and is not part of the submission.
