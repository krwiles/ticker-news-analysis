# Secrets management: per-service file secrets, fail-fast startup, and a bootstrap script

Roadmap Phase 2 (`NOTES.md`). Architecture and reasoning live in `docs/adr/0017-secrets-management.md`; this is
the build order. No spec — no user-visible behavior changes. The goal, in the user's words: learn how secrets
management is used in a production, publicly-deployed system, and build it production-shaped even though it runs
locally. Vault stays deferred to Phase 4.

## What changes

| File | Change |
| --- | --- |
| `docker-compose.yml` | Split the shared `&app-env` anchor into a non-secret `&data-env` plus per-service extras; top-level `secrets:` block; per-service `secrets:` lists; `db` uses `POSTGRES_PASSWORD_FILE`; data-store ports bind `127.0.0.1`. |
| `backend/src/ticker_backend/config.py` | `secrets_dir`; `postgres_*` fields and a `database_url` **property** (SQLAlchemy `URL.create`); `sentiment_configured`; `require_secrets()`. |
| `main.py`, `worker.py` | `create_app()` and ARQ's `on_startup` call `require_secrets()`. |
| `search.py` | `_compute_sentiment_status` reads `sentiment_configured`, not the OpenAI key. |
| `scripts/init-secrets.sh` | New: hidden prompts, mode-600 files, idempotent, `--from-env`, `--rotate NAME`. |
| `providers.py`, `logging.py` | Finnhub key moves from a `?token=` URL param to an `X-Finnhub-Token` header; `httpx` logger raised to WARNING (found during verification — see below). |
| `.gitignore`, `.env.example`, `README.md`, CI | `secrets/` ignored; keys removed from `.env.example`; runbook + provider checklist; CI runs `docker compose config -q` with dummy secrets. |

## Order of work (TDD at each code seam)

1. `config.py` tests first (file read, env-outranks-file, DSN escaping, per-mode required secrets), then the code.
2. `create_app()` / worker startup tests, then the wiring; `conftest.py` seeds `POSTGRES_PASSWORD` before any import.
3. `init-secrets.sh` tests (run the real script against a temp dir via `SECRETS_DIR`/`ENV_FILE`), then the script.
4. Compose restructure; run `--from-env` on the real `.env`; rebuild; verify live.
5. ADR, README, NOTES; lessons 0038/0039.

## Tests

- `test_config.py`: secret file read (newline stripped); an env var silently outranks the file; DSN password with
  `@:/#` round-trips and is percent-encoded; api needs the Postgres password; worker also needs Finnhub; OpenAI is
  never required and `ui` needs nothing.
- `test_main.py`, `test_worker.py`: startup refuses to run without required secrets; `ui` builds with none.
- `test_init_secrets.py`: `--from-env` moves keys, strips `.env`, keeps other lines, prints no value; re-run never
  overwrites; OpenAI optional flips `SENTIMENT_CONFIGURED`; `--rotate` touches one file; a required secret can't
  be empty.
- `test_providers.py` / `test_logging.py`: the Finnhub key is in a header and never in the URL; `httpx` INFO logging is off.
- `test_search_endpoint.py`: the four sentiment-status tests now drive `sentiment_configured`.
- Deliberate-break checks: disabled `require_secrets`' check and the script's `.env` stripping; confirmed the
  relevant tests failed, then reverted.

## Verification (live, against the real stack)

`docker compose exec` per service: `ui` has no secrets, `api` only the Postgres password, `worker` all three; no
key-named variable in any environment. A scratch Postgres with a fresh data directory proved `POSTGRES_PASSWORD_
FILE` works with a mode-600 file. A real search on an uncached ticker exercised Finnhub, embeddings, and sentiment
end to end. The same image with no secrets mounted exits with the named error in both `api` and `worker` mode.

## What actually happened during execution

Built as planned, with these deviations and findings:

- **`${OPENAI_API_KEY:+true}` was unworkable, so `SENTIMENT_CONFIGURED` is an explicit flag.** The grilled design
  derived `api`'s boolean from Compose interpolation of the OpenAI key — but once the key leaves `.env`, Compose
  has nothing to interpolate. `init-secrets.sh` now writes `SENTIMENT_CONFIGURED=true|false` into `.env` whenever
  it writes the OpenAI secret. Trade-off: a hand-edit can make the flag and key disagree.
- **`database_url` became a property returning a `URL` object, not a string.** `db.py` needed no change because
  `create_async_engine` accepts either.
- **Tests had to opt out of ambient env vars.** Env outranks `secrets_dir` — the very footgun the ADR documents
  — so my own shell's `POSTGRES_PASSWORD` broke two tests until a fixture cleared it.
- **arq connects to Redis before `on_startup`.** The worker's fail-fast error therefore appears only once Redis is
  reachable; verified on the compose network.
- **Two tooling slips, both caught:** a first compose rewrite matched an early `volumes:` and mangled the file
  (restored from git and redone with anchored edits), and macOS `sed` rejected my first deliberate break, so the
  "failing" run was really passing until I redid it in Python.
- **Existing Postgres volumes don't re-read the password file.** The live stack's `db` never exercised
  `POSTGRES_PASSWORD_FILE`, hence the scratch-container check — and the ALTER USER step in the rotation runbook.
- **The Finnhub key was being printed in the worker logs.** Reading `providers.py` while writing lesson 39 showed
  the key sent as `?token=`; `docker compose logs worker` confirmed `httpx` logged the full URL, key included, on
  every fetch. File-based storage doesn't touch that path. Fixed test-first (header, not URL) plus a logging
  guard; the first version of the logging test passed even with the fix removed (pytest leaves the root logger
  at WARNING), caught by the deliberate-break check and rewritten. Verified live: zero occurrences of the key or
  `HTTP Request` lines in the rebuilt worker's logs, Finnhub still `ok`. The key sat in local container logs
  until those containers were recreated; consider rotating it (README runbook) if the machine is shared.
- **Code review found two real gaps and a style violation, all fixed:** `require_secrets()` silently allowed an
  unrecognized `APP_MODE` (the `.get(mode, [])` default), which only `main.py`'s own `match/case` would have caught
  for `api`/`ui` — `worker` has no such guard, so a typo'd mode would have booted with no secrets required. Now
  rejected explicitly, test-first. `api`'s `/api/health` calls `check_milvus`, but `MILVUS_URI` wasn't in its
  environment — it happened to work only because the code default matches the compose service name; moved into
  the shared `&data-env` so both `api` and `worker` get it explicitly, and ADR 0017's table corrected.
  `init-secrets.sh`'s 5-line header comment violated this repo's comment-length convention; trimmed, with the
  usage detail it held living only in the README (no duplication). A fourth finding — `.env`'s `DATABASE_URL` and
  `./secrets/postgres_password` are two sources of truth for one password with nothing checking they match — was
  already covered by the README's rotation runbook, so no further change.
- **Not done, recorded in ADR 0017:** MinIO/Milvus shared credentials, Redis `requirepass`, non-default dev
  passwords.
