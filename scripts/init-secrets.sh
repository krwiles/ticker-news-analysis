#!/usr/bin/env bash
# Creates the file-based secrets Compose mounts at /run/secrets (docs/adr/0017-*.md); see README for usage.
# Safe to re-run -- an existing secret file is never overwritten, and no value is ever printed.

set -euo pipefail

# Paths are overridable so the tests can run this against a throwaway directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$REPO_ROOT/secrets}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

FROM_ENV=false
ROTATE=""

# Parse the two supported flags.
while [ $# -gt 0 ]; do
  case "$1" in
    --from-env) FROM_ENV=true ;;
    --rotate) ROTATE="${2:-}"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# Owner-only from the first byte: every file and directory below is created under this umask.
umask 077
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# A rotation is just "forget this one file, then prompt for it like a fresh setup".
if [ -n "$ROTATE" ]; then
  case "$ROTATE" in
    finnhub_api_key|openai_api_key|postgres_password) rm -f "$SECRETS_DIR/$ROTATE" ;;
    *) echo "unknown secret: $ROTATE" >&2; exit 2 ;;
  esac
fi

# Reads KEY=value from .env, stripping one layer of surrounding quotes. Prints nothing if absent.
env_value() {
  [ -f "$ENV_FILE" ] || return 0
  { grep -E "^$1=" "$ENV_FILE" || true; } | tail -1 | cut -d= -f2- | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

# Removes every KEY= line from .env, via a temp file so a failure can't leave it half-written.
strip_from_env() {
  [ -f "$ENV_FILE" ] || return 0
  local tmp
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  { grep -vE "^$1=" "$ENV_FILE" || true; } > "$tmp"
  mv "$tmp" "$ENV_FILE"
}

# Sets KEY=value in .env (replace or append) -- only ever used for non-secret flags.
set_env_flag() {
  strip_from_env "$1"
  printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
}

# Writes one secret file with no trailing newline, owner-read/write only.
write_secret() {
  printf '%s' "$2" > "$SECRETS_DIR/$1"
  chmod 600 "$SECRETS_DIR/$1"
}

# Hidden prompt (read -s suppresses echo on a terminal); the prompt text goes to stderr.
prompt_hidden() {
  local value
  read -r -s -p "$1" value || true
  echo >&2
  printf '%s' "$value"
}

# Handles one secret: skip if present, else take it from .env (--from-env), else prompt.
# $1 = file name, $2 = .env key, $3 = "required" | "optional", $4 = prompt text.
ensure_secret() {
  local name="$1" env_key="$2" kind="$3" prompt="$4" value=""
  if [ -f "$SECRETS_DIR/$name" ]; then
    echo "kept    $name (already exists)"
    # A leftover .env line would still override the file at runtime (env outranks secrets_dir).
    if [ -n "$(env_value "$env_key")" ]; then
      echo "warning: .env still sets $env_key -- it overrides the file; remove that line" >&2
    fi
    return 0
  fi

  if [ "$FROM_ENV" = true ] && [ -z "$ROTATE" ]; then
    value="$(env_value "$env_key")"
  fi

  if [ -z "$value" ]; then
    value="$(prompt_hidden "$prompt")"
  else
    strip_from_env "$env_key"
  fi

  # Postgres has a documented local-dev default (host tooling's URLs in .env use it); nothing else does.
  if [ -z "$value" ] && [ "$name" = "postgres_password" ]; then
    value="ticker"
  fi

  if [ -z "$value" ] && [ "$kind" = "required" ]; then
    echo "error: $name is required" >&2
    exit 1
  fi

  write_secret "$name" "$value"
  echo "created $name"
}

ensure_secret postgres_password POSTGRES_PASSWORD required \
  "Postgres password (Enter for the local-dev default; must match DATABASE_URL in .env): "
ensure_secret finnhub_api_key FINNHUB_API_KEY required "Finnhub API key: "
ensure_secret openai_api_key OPENAI_API_KEY optional "OpenAI API key (Enter to skip -- sentiment stays off): "

# api never sees the OpenAI key, so tell it (non-secret) whether sentiment is on.
if [ -s "$SECRETS_DIR/openai_api_key" ]; then
  set_env_flag SENTIMENT_CONFIGURED true
else
  set_env_flag SENTIMENT_CONFIGURED false
fi

echo "done -- secrets are in $SECRETS_DIR (gitignored). Run: docker compose up -d --build"
