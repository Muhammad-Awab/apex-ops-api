#!/usr/bin/env bash
# Run the same quality gates as .github/workflows/ci.yml locally (Docker only, no local Python).
# Stops at the first failing gate, the same way CI's `needs:` stops later jobs.
#   scripts/ci_local.sh                              # all gates
#   scripts/ci_local.sh --with-intentional-failure   # proves a failing test blocks the release
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=ci

INTENTIONAL=0
[ "${1:-}" = "--with-intentional-failure" ] && INTENTIONAL=1

DEV_IMAGE=apex-ops-api:dev
CI_IMAGE="$APP_IMAGE:ci-local"
RESULTS=()

summary() {
  log "------------------------------------------------------------"
  for r in "${RESULTS[@]}"; do log "$r"; done
}

gate() {  # gate <name> <command...>
  local name="$1"; shift
  log "==> $name"
  if "$@"; then
    RESULTS+=("PASS  $name")
  else
    RESULTS+=("FAIL  $name")
    summary
    log "RELEASE BLOCKED: '$name' failed - no image is built, scanned or published."
    exit 1
  fi
}

# MSYS_NO_PATHCONV stops Git Bash on Windows rewriting container paths (/tmp/...) into C:/...
in_dev() { MSYS_NO_PATHCONV=1 docker run --rm -e RUN_INTENTIONAL_FAILURE="$INTENTIONAL" "$DEV_IMAGE" "$@"; }

gate "build test image"          docker build -q --target dev -t "$DEV_IMAGE" "$ROOT"
gate "lint (ruff check)"         in_dev ruff check .
gate "format (ruff format)"      in_dev ruff format --check .
gate "unit tests + coverage>=80" in_dev pytest --cov=app --cov-report=term
gate "dependency audit (pip-audit)" in_dev pip-audit --strict --progress-spinner off -r /tmp/requirements.txt
gate "Dockerfile lint (hadolint)" sh -c "docker run --rm -i hadolint/hadolint:v2.12.0 hadolint --failure-threshold warning - < '$ROOT/Dockerfile'"
gate "build runtime image"       docker build -q --target runtime --build-arg APP_VERSION=0.0.0-ci \
                                   --build-arg GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)" \
                                   -t "$CI_IMAGE" "$ROOT"
gate "image runs as non-root"    test "$(docker image inspect -f '{{.Config.User}}' "$CI_IMAGE")" = "10001:10001"
gate "image scan (trivy HIGH/CRITICAL)" env MSYS_NO_PATHCONV=1 docker run --rm \
                                   -v /var/run/docker.sock:/var/run/docker.sock -v apex-trivy-cache:/root/.cache \
                                   aquasec/trivy:0.58.1 image --quiet --scanners vuln --ignore-unfixed \
                                   --severity HIGH,CRITICAL --exit-code 1 "$CI_IMAGE"
gate "compose file valid"        env APP_VERSION=0.0.0-ci docker compose -f "$ROOT/docker-compose.yml" --env-file "$ROOT/.env.example" config -q
gate "alert rules valid (promtool)" sh -c "docker run --rm -i --entrypoint sh prom/prometheus:v2.55.1 \
                                   -c 'cat > /tmp/rules.yml && promtool check rules /tmp/rules.yml' < '$ROOT/monitoring/alert_rules.yml'"

summary
log "ALL GATES PASSED - image $CI_IMAGE is releasable."
