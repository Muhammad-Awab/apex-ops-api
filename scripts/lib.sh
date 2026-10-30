#!/usr/bin/env bash
# Shared helpers for deploy/rollback/smoke scripts. Source, don't execute.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$ROOT/scripts"
ENV_FILE="$ROOT/.env"
STATE_DIR="$ROOT/.deploy"
HISTORY="$STATE_DIR/history.log"
LOCK_DIR="$STATE_DIR/lock"

# Read a key from .env without sourcing it (never execute config files).
env_get() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 || true; }

APP_IMAGE="$(env_get APP_IMAGE)"; APP_IMAGE="${APP_IMAGE:-apex-ops-api}"
APP_PORT="$(env_get APP_PORT)"; APP_PORT="${APP_PORT:-8080}"
BASE_URL="http://127.0.0.1:${APP_PORT}"

log()  { printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${LOG_TAG:-release}" "$*"; }
die()  { log "ERROR: $*" >&2; exit 1; }

compose() { docker compose --project-directory "$ROOT" -f "$ROOT/docker-compose.yml" "$@"; }

preflight() {
  [ -f "$ENV_FILE" ] || die ".env missing - run scripts/init_secrets.sh"
  [ -s "$ROOT/secrets/db_password.txt" ] || die "secrets/db_password.txt missing - run scripts/init_secrets.sh"
  docker info >/dev/null 2>&1 || die "docker daemon not reachable"
  mkdir -p "$STATE_DIR"
}

acquire_lock() {
  [ "${DEPLOY_LOCK_HELD:-0}" = "1" ] && return 0
  mkdir "$LOCK_DIR" 2>/dev/null || die "another deploy/rollback is in progress (remove $LOCK_DIR if stale)"
  export DEPLOY_LOCK_HELD=1
  trap 'rm -rf "$LOCK_DIR"' EXIT
}

image_exists() { docker image inspect "$APP_IMAGE:$1" >/dev/null 2>&1; }

configured_version() { env_get APP_VERSION; }

set_version() {
  # Single source of truth for what compose runs; edited in place, rest of .env untouched.
  sed -i.bak "s/^APP_VERSION=.*/APP_VERSION=$1/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
}

record() {  # record <action> <version> <result>
  printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" >> "$HISTORY"
}

# Most recent version that was deployed/rolled back successfully, excluding $1.
last_good_except() {
  [ -f "$HISTORY" ] || return 0
  awk -v skip="${1:-}" '$4 == "success" && $3 != skip { v = $3 } END { if (v) print v }' "$HISTORY"
}

http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$@" || true; }

wait_ready() {  # wait_ready <timeout_seconds>
  local timeout="$1" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if [ "$(http_code "$BASE_URL/readyz")" = "200" ]; then
      log "readiness OK after ${waited}s"
      return 0
    fi
    sleep 2; waited=$((waited + 2))
  done
  log "readiness NOT OK after ${timeout}s: $(curl -s --max-time 3 "$BASE_URL/readyz" || echo 'no response')"
  return 1
}

# Switch the app service to the given image version and verify it.
roll_to() {  # roll_to <version>
  # Explicit `|| return 1`: set -e is suspended when called from an `if`.
  set_version "$1" || return 1
  compose up -d --wait db || return 1
  compose up -d --no-deps --force-recreate app || return 1
  wait_ready "${READY_TIMEOUT:-60}" || return 1
  "$SCRIPT_DIR/smoke_test.sh" "$1"
}
