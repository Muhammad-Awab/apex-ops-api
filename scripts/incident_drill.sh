#!/usr/bin/env bash
# Failure investigation drill: simulate a database outage and walk the runbook.
#   scripts/incident_drill.sh
# Detect -> triage -> diagnose -> remediate -> verify (incl. data persisted across the outage).
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=drill

step() { printf '\n===== %s =====\n' "$*"; }
probe() { printf '%-10s HTTP %s  %s\n' "$1" "$(http_code "$BASE_URL$1")" "$(curl -s --max-time 3 "$BASE_URL$1")"; }

step "0. Baseline"
probe /healthz
probe /readyz
MARKER="drill-$(date +%s)"
curl -s -X POST "$BASE_URL/api/v1/incidents" -H 'Content-Type: application/json' \
  -H "X-Request-ID: $MARKER" -d "{\"title\":\"pre-outage record $MARKER\",\"severity\":\"medium\"}"
echo

PROM_URL="http://127.0.0.1:9090"
OUTAGE_SECONDS="${OUTAGE_SECONDS:-5}"   # use ~100 with the monitoring profile to see the alert fire

step "1. Inject failure: stop the database container (outage held ${OUTAGE_SECONDS}s)"
compose stop db
sleep "$OUTAGE_SECONDS"

step "2. Detect: probes, metrics and alerts as seen by monitoring"
probe /healthz
probe /readyz
curl -s "$BASE_URL/metrics" | grep -E '^apex_db_up|^apex_http_requests_total\{.*readyz.*503' || true
if [ "$(http_code "$PROM_URL/-/ready")" = 200 ]; then
  echo "Prometheus alerts:"
  curl -s "$PROM_URL/api/v1/alerts" | grep -oE '"alertname":"[A-Za-z]+"|"state":"[a-z]+"' | paste - - || true
else
  echo "(Prometheus not running - start with: docker compose --profile monitoring up -d prometheus)"
fi

step "3. Triage: what is running?"
compose ps --all --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'

step "4. Diagnose: structured app logs (filter by event)"
compose logs --no-log-prefix --since 30s app | grep -E '"event": "(readiness_failed|http_request)"' | grep -E 'readiness_failed|"status": 503' | tail -3

step "5. Remediate: start the database again"
compose start db
compose up -d --wait db
wait_ready 60

step "6. Verify recovery and data durability"
probe /readyz
if curl -s "$BASE_URL/api/v1/incidents?limit=200" | grep -q "pre-outage record $MARKER"; then
  echo "record created before the outage is still present -> volume persistence OK"
else
  echo "WARNING: pre-outage record not found"; exit 1
fi
curl -s "$BASE_URL/metrics" | grep -E '^apex_db_up'
log "drill complete"
