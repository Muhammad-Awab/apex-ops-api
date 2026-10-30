# Evidence of execution

Every log below is **unedited script output** captured on 2026-10-30 (UTC timestamps), on Windows 11 with Docker Desktop 29.1.3 / Compose v2.40, using Git Bash. Each one can be regenerated with the command shown. The only change: in `11_security_posture.log` the local OS username was replaced with `user group`.

| # | Claim | Evidence | Reproduce with |
|---|-------|----------|----------------|
| 01 | All 11 quality gates pass: lint, format, 17 unit tests (98% coverage), pip-audit (0 vulns), hadolint, build, non-root check, Trivy (0 HIGH/CRITICAL), compose validation, promtool | [01_ci_local_pass.log](01_ci_local_pass.log) | `bash scripts/ci_local.sh` |
| 02 | **Intentional failure**: a failing test stops the pipeline. No image is built, scanned or published | [02_ci_local_intentional_failure.log](02_ci_local_intentional_failure.log) | `bash scripts/ci_local.sh --with-intentional-failure` |
| 03a | The first deploy failed because of a **bug in my own smoke test** (`docker compose port` prints `:0` for unpublished ports). The gate refused to mark the release good, as designed. Fixed in `smoke_test.sh` | [03a_first_deploy_smoke_test_bug.log](03a_first_deploy_smoke_test_bug.log) | historical |
| 03 | Deploy v1.0.0: readiness-gated, 8/8 smoke checks | [03_deploy_v1.0.0.log](03_deploy_v1.0.0.log) | `bash scripts/deploy.sh 1.0.0` |
| 04 | Upgrade to v1.1.0 | [04_deploy_v1.1.0.log](04_deploy_v1.1.0.log) | `bash scripts/deploy.sh 1.1.0` |
| 05 | **Bad release v1.2.0** (readiness never passes) is rejected and **auto-rolled back** to 1.1.0; `deploy.sh` exits 1 | [05_bad_release_1.2.0_auto_rollback.log](05_bad_release_1.2.0_auto_rollback.log) | `scripts/build.sh 1.2.0 --fault not_ready && scripts/deploy.sh 1.2.0` |
| 06 | **Bad release v1.3.0** passes health checks but returns 5xx on the API. The functional smoke tests catch it and it is auto-rolled back | [06_bad_release_1.3.0_smoke_fail_auto_rollback.log](06_bad_release_1.3.0_smoke_fail_auto_rollback.log) | `scripts/build.sh 1.3.0 --fault errors && scripts/deploy.sh 1.3.0` |
| 07 | **Manual rollback** 1.1.0 → 1.0.0, roll forward to 1.1.0, release history, versioned images, and data persisting across every release (8 records) | [07_manual_rollback_and_history.log](07_manual_rollback_and_history.log) | `bash scripts/rollback.sh` |
| 08 | v1.4.0: fix so `apex_db_up` is refreshed on every Prometheus scrape (found while preparing the drill) | [08_deploy_v1.4.0_metrics_fix.log](08_deploy_v1.4.0_metrics_fix.log) | `bash scripts/deploy.sh 1.4.0` |
| 09a | **Failure investigation, finding:** during the DB-outage drill `/readyz` took 3.8 s, longer than the 3 s probe timeout, so probes saw a timeout instead of a 503 | [09a_incident_drill_finding_slow_readiness.log](09a_incident_drill_finding_slow_readiness.log) | historical |
| 10 | v1.5.0 + compose `dns_opt` fix deployed | [10_redeploy_v1.5.0_dns_timeout_fix.log](10_redeploy_v1.5.0_dns_timeout_fix.log) | `bash scripts/deploy.sh 1.5.0` |
| 09 | **Incident drill after the fix:** DB outage gives liveness 200, readiness 503 in ~1.0 s, `apex_db_up 0`, Prometheus alert `ApexDatabaseUnreachable` **firing**. After recovery: ready, data intact | [09_incident_drill_db_outage.log](09_incident_drill_db_outage.log) | `docker compose --profile monitoring up -d prometheus && OUTAGE_SECONDS=100 bash scripts/incident_drill.sh` |
| 11 | Security posture: secret absent from env/inspect/logs, uid 10001, read-only rootfs, all capabilities dropped, no-new-privileges, DB not exposed, internal backend network | [11_security_posture.log](11_security_posture.log) | commands in the log header (see `docs/SECURITY.md`) |

## GitHub Actions (CI/CD on GitHub)

| Claim | Evidence |
|-------|----------|
| **Full pipeline green on GitHub:** lint/tests/audit, hadolint, then build + Trivy + Compose integration + bad-release auto-rollback test, then publish. Run #7, commit `e5139c7`, 3m 38s. Image published as `ghcr.io/muhammad-awab/apex-ops-api:0.0.0-sha.e5139c7` (exact image that was tested, promoted without rebuild) | [ci-green.png](ci-green.png) |
| **Intentional failure on GitHub:** manual run with `demo_intentional_failure=true`. `test_intentional_failure_blocks_release` fails (`1 failed, 17 passed`), and **Build/scan/integration and Publish are skipped**. Nothing is released | [ci-intentional-failure.png](ci-intentional-failure.png) |
| **First GitHub run failed, and the gate held.** The integration job failed with `scripts/smoke_test.sh: Permission denied`: the executable bit is lost when committing from Windows. `deploy.sh` refused to mark the release good and nothing was published. Fixed by invoking helper scripts through `bash` (commit `e5139c7`) | kept in the repository's Actions history |
