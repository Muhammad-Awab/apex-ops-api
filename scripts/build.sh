#!/usr/bin/env bash
# Build an immutable, versioned runtime image.
#   scripts/build.sh 1.1.0
#   scripts/build.sh 1.2.0 --fault not_ready   # deliberately broken release (rollback demo)
#   scripts/build.sh 1.1.0 --force             # overwrite an existing tag (avoid in practice)
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
LOG_TAG=build

VERSION="${1:?usage: build.sh <version> [--fault none|not_ready|errors] [--force]}"
shift
FAULT=none FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --fault) FAULT="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) die "unknown option $1" ;;
  esac
done

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]] || die "version must be semver, got '$VERSION'"
if image_exists "$VERSION" && [ "$FORCE" != 1 ]; then
  die "$APP_IMAGE:$VERSION already exists - versions are immutable, pick a new version (or --force)"
fi

GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
log "building $APP_IMAGE:$VERSION (git_sha=$GIT_SHA fault_mode=$FAULT)"
docker build --target runtime \
  --build-arg APP_VERSION="$VERSION" \
  --build-arg GIT_SHA="$GIT_SHA" \
  --build-arg FAULT_MODE="$FAULT" \
  --label "com.apex.fault_mode=$FAULT" \
  -t "$APP_IMAGE:$VERSION" "$ROOT"
log "built $APP_IMAGE:$VERSION ($(docker image inspect -f '{{.Id}}' "$APP_IMAGE:$VERSION" | cut -c1-19))"
