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

## Not yet evidenced (needs the candidate's GitHub account)

The GitHub Actions workflow (`.github/workflows/ci.yml`) was validated with `actionlint` and mirrors `scripts/ci_local.sh` step for step. It has **not been run on GitHub from this machine**, because there was no repository or credentials here. To add that evidence:

1. Push the repo to GitHub and open the **Actions** tab. Screenshot the green run (`ci-green.png`).
2. Go to **Actions → CI/CD → Run workflow**, tick `demo_intentional_failure`, and screenshot the red `test` job with the skipped downstream jobs (`ci-intentional-failure.png`).
3. Save the screenshots in this folder.
