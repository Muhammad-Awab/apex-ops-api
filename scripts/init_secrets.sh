#!/usr/bin/env bash
# One-time local setup: create .env from the template and generate a random DB password.
# Idempotent - existing files are never overwritten.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "created .env from .env.example"
fi

SECRET="$ROOT/secrets/db_password.txt"
if [ ! -s "$SECRET" ]; then
  mkdir -p "$ROOT/secrets"
  umask 077
  # 32 random alphanumeric chars; never printed.
  # (read a fixed amount first - `tr </dev/urandom | head` dies with SIGPIPE under pipefail)
  PW="$(head -c 512 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')"
  printf '%s' "${PW:0:32}" > "$SECRET"
  unset PW
  # Directory private to the owner; file readable inside containers (uid 10001 / postgres).
  chmod 700 "$ROOT/secrets"; chmod 644 "$SECRET"
  echo "generated secrets/db_password.txt"
else
  echo "secrets/db_password.txt already exists - left unchanged"
fi
