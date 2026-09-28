# Secrets are per-service files mounted at `/run/secrets`, not shared environment variables

Status: accepted — supersedes the "shared `&app-env` anchor" arrangement in `docker-compose.yml` (see ADR 0001)

Before this, every secret sat in `.env`, was interpolated into one shared `&app-env` anchor, and so landed as a
plain environment variable in **all three** containers — including `ui`, which serves static files and calls
nothing. Only `worker` ever used the Finnhub and OpenAI keys. Environment variables leak in ways files don't
(`docker inspect`, `/proc/<pid>/environ`, crash dumps, and any tool that prints `env`), and a compromise of the
least-defended container (`ui`) exposed every key. The goal of this work is the shape a public deployment
needs, run locally: the mechanism is production-shaped even though the secret store is not yet.

## Least privilege per service, still one image

Each mode gets only what it uses. The single image and `APP_MODE` (ADR 0001) are untouched — the split is in
what Compose *gives* each container, not in what is built.

| Service | Secrets mounted | Non-secret config |
| --- | --- | --- |
| `worker` | Postgres password, Finnhub key, OpenAI key | DB/Redis/Milvus, SEC user agent |
| `api` | Postgres password | DB/Redis, Google client ID, `SENTIMENT_CONFIGURED` |
| `ui` | none | none |

`api` needs one fact about the OpenAI key — *is sentiment on?* (`search.py` reports `skipped` when it isn't).
It gets a non-secret boolean, `SENTIMENT_CONFIGURED`, instead of the key. `scripts/init-secrets.sh` writes that
flag whenever it writes the OpenAI secret, so the two only drift if someone hand-edits one of them.

## Files, not environment variables

Compose's file-based `secrets:` mounts each secret at `/run/secrets/<name>`, read via `pydantic-settings`'
`secrets_dir` (files are named after the `Settings` fields). `db` uses the postgres image's native
`POSTGRES_PASSWORD_FILE`. The app assembles its database URL from parts (`Settings.database_url`), using
SQLAlchemy's `URL.create` so a password with `@`, `:`, or `#` cannot corrupt the URL.

**The interface is "a file at a path".** A future Vault Agent, Kubernetes Secret volume, or cloud secret
manager's CSI driver all deliver secrets the same way, so Phase 4 changes where the file *comes from*, not what
the app reads. This is why Vault itself is deferred rather than skipped.

**Precedence footgun, kept on purpose and documented:** `pydantic-settings` ranks environment variables *above*
`secrets_dir`. A stale key left in `.env` would silently override the mounted file. `init-secrets.sh --from-env`
therefore strips moved keys out of `.env`, and warns if one is left behind.

**Considered:** a single `secrets.env` file loaded as env vars (rejected: same leak paths as before, and
no per-service scoping); Docker Swarm secrets (rejected: requires Swarm mode for no gain here); Vault now
(deferred, Phase 4: a large tool to learn for four secrets, and the file interface keeps the door open).

## Secrets must also stay out of logs

Where a secret is *stored* is only half of it — it must not be *printed*. Found while verifying this work:
`providers.py` sent the Finnhub key as a `?token=` query parameter, and `httpx` logs every request URL at INFO,
so the worker printed the live key on every fetch. Finnhub also accepts an `X-Finnhub-Token` header (verified
against the live API, including that a wrong value is rejected), so the key now travels in the header, and
`configure_logging()` raises `httpx`'s logger to WARNING as a second layer. Moving a key to a file would not
have fixed this: it was the *use* of the key that leaked it.

## Missing secrets fail fast; OpenAI stays optional

The Finnhub key and Postgres password are required in the modes that use them. `require_secrets()` runs from
`create_app()` and the worker's `on_startup` hook and exits with a message naming the missing secret (never its
value). It cannot live in `Settings` itself: `Settings()` is built at import time and tests import with no
secrets present. The OpenAI key stays optional — spec 0005 designed sentiment to degrade, not fail.

## Bootstrap, and the boundary of what this covers

`scripts/init-secrets.sh` creates `./secrets/` (gitignored, mode 700, files 600) from hidden prompts,
idempotently; `--from-env` migrates existing keys out of `.env` without printing them; `--rotate NAME`
replaces one secret. Host-side tools (`dbmate`, pytest) cannot read `/run/secrets`, so `.env` keeps a
documented local-only `DATABASE_URL`/`TEST_DATABASE_URL` (`ticker`/`ticker`) that must match the secret.

Every data-store port (Postgres, Redis, MinIO, Milvus) now publishes on `127.0.0.1` only; `api` and `ui` remain
the intended public surface. Redis holds live session IDs (ADR 0016) and has no password.

**Accepted, not fixed here:**
- **MinIO/Milvus still share the well-known `minioadmin` credentials.** Changing them means coordinated
  changes in two services (lesson 16's MinIO breakage is the precedent), and loopback binding removes the
  exposure meanwhile. Recorded as a known remaining item.
- **Redis has no `requirepass`, and Postgres/MinIO passwords stay weak dev values.** Fine on loopback; both
  are required steps before any real deployment.
- **Files on disk are plaintext.** They rely on filesystem permissions and the gitignore; encryption at rest,
  audit logs, dynamic short-lived credentials, and automatic rotation are what Vault (Phase 4) adds.
- **An existing Postgres volume keeps the password it was initialised with.** Rotating `postgres_password`
  needs an `ALTER USER` as well — see the README runbook.
