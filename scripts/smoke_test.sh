#!/usr/bin/env bash
# Post-deploy smoke tests against the running stack.
#   scripts/smoke_test.sh [expected_version]
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=smoke

EXPECTED="${1:-$(configured_version)}"
PASS=0 FAIL=0
check() {  # check <description> <command...>
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then PASS=$((PASS + 1)); log "PASS  $name"
  else FAIL=$((FAIL + 1)); log "FAIL  $name"; fi
}

body() { curl -s --max-time 3 "$@"; }
# Note: `compose port db 5432` prints ":0" and exits 0 for unpublished ports, so inspect instead.
db_port_closed() {
  test "$(docker inspect -f '{{json (index .NetworkSettings.Ports "5432/tcp")}}' "$(compose ps -q db)")" = null
}

check "liveness /healthz returns 200" test "$(http_code "$BASE_URL/healthz")" = 200
check "readiness /readyz returns 200" test "$(http_code "$BASE_URL/readyz")" = 200
check "running version is $EXPECTED" grep -q "\"version\":\"$EXPECTED\"" <<<"$(body "$BASE_URL/version")"

CREATED="$(body -X POST "$BASE_URL/api/v1/incidents" -H 'Content-Type: application/json' \
  -d '{"title":"smoke test incident","severity":"low"}' || true)"
ID="$(sed -nE 's/.*"id":([0-9]+).*/\1/p' <<<"$CREATED")"
check "POST /api/v1/incidents creates a record" test -n "$ID"
check "GET /api/v1/incidents/{id} reads it back" test "$(http_code "$BASE_URL/api/v1/incidents/${ID:-0}")" = 200
check "/metrics exposes request counters" grep -q apex_http_requests_total <<<"$(body "$BASE_URL/metrics")"
check "app container runs as non-root (uid 10001)" \
  test "$(compose exec -T app python -c 'import os; print(os.getuid())' | tr -d '\r')" = 10001
check "database port is not published to the host" db_port_closed

log "result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
