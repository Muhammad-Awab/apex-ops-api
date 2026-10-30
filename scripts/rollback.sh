#!/usr/bin/env bash
# Roll back to a previous image version.
#   scripts/rollback.sh            # previous known-good version from .deploy/history.log
#   scripts/rollback.sh 1.0.0      # explicit version
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=rollback

preflight
acquire_lock

CURRENT="$(configured_version)"
TARGET="${1:-$(last_good_except "$CURRENT")}"
[ -n "$TARGET" ] || die "no previous successful release in $HISTORY - pass a version explicitly"
image_exists "$TARGET" || docker pull -q "$APP_IMAGE:$TARGET" >/dev/null 2>&1 \
  || die "image $APP_IMAGE:$TARGET not found locally or in the registry"

log "rolling back: $CURRENT -> $TARGET"
if roll_to "$TARGET"; then
  record rollback "$TARGET" success
  log "SUCCESS: rolled back to $TARGET"
else
  record rollback "$TARGET" failed
  die "rollback to $TARGET failed health checks - escalate (docs/RUNBOOK.md)"
fi
