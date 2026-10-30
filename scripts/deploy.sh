#!/usr/bin/env bash
# Deploy a versioned image with health gating and automatic rollback.
#   scripts/deploy.sh <version>
# Steps: preflight -> lock -> start db -> switch app image -> wait /readyz -> smoke tests
#        success: record it | failure: capture diagnostics, roll back to last good version
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=deploy

VERSION="${1:?usage: deploy.sh <version>}"
preflight
acquire_lock
if ! image_exists "$VERSION"; then
  # With APP_IMAGE=ghcr.io/<owner>/apex-ops-api in .env, CI-published versions are pulled here.
  log "image $APP_IMAGE:$VERSION not found locally - trying registry pull"
  docker pull -q "$APP_IMAGE:$VERSION" >/dev/null 2>&1 \
    || die "image $APP_IMAGE:$VERSION not found - build it (scripts/build.sh $VERSION) or publish it via CI"
fi

LAST_GOOD="$(last_good_except "$VERSION")"
log "deploying $APP_IMAGE:$VERSION (last known good: ${LAST_GOOD:-none})"

if roll_to "$VERSION"; then
  record deploy "$VERSION" success
  log "SUCCESS: $VERSION is live at $BASE_URL"
  exit 0
fi

record deploy "$VERSION" failed
log "FAILED: $VERSION did not pass readiness/smoke checks. Last 20 app log lines:"
compose logs --no-log-prefix --tail 20 app || true

if [ -z "$LAST_GOOD" ]; then
  log "no previous good version to roll back to - leaving stack as is for investigation"
  exit 1
fi

log "AUTO-ROLLBACK to $LAST_GOOD"
"$SCRIPT_DIR/rollback.sh" "$LAST_GOOD" || die "auto-rollback failed - follow docs/RUNBOOK.md (manual rollback)"
exit 1   # the requested release still failed
