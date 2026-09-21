# Ticker News Analysis

A tool for gathering and surfacing news and SEC filings about publicly-traded companies, searchable by ticker
symbol — search a ticker (e.g. `AAPL`), get its most recent news and filings from the past week, fetched live
and concurrently from multiple providers.

## Why this repo exists

This is a real, working application, but it's also deliberately serving two other purposes at the same time:

- **Learning a specific tech stack hands-on**, by actually building something with it end to end rather than
  following boilerplate tutorials: Python/FastAPI/SQLAlchemy (async ORM)/Postgres, Redis + ARQ (background jobs),
  React/TypeScript/React Router/Tailwind/Webpack, and Docker. The goal is real fluency — being able to write a
  new endpoint, model, and migration from scratch, or add a new background job, or build a new page, without
  copy-pasting from what's already here.
- **Practicing spec-driven development and AI-assisted coding as disciplines.** Every non-trivial feature
  starts as a written spec and a domain model before any code, architectural decisions get written down as ADRs
  before they're implemented, and the whole thing is built collaboratively with an AI coding assistant acting as
  both pair programmer and teacher — the repo intentionally keeps that process visible rather than squashing it
  away.

## Repo layout

```
backend/          FastAPI + SQLAlchemy (async) + ARQ — the API, background worker, and static-file server
frontend/          React + TypeScript + React Router + Tailwind, built with Webpack
db/migrations/     Plain-SQL migrations (dbmate) — the source of truth for the schema
docs/specs/        Feature specs, written before implementation
docs/adr/          Architecture decision records — what was decided, what was considered, and why
docs/plans/         Per-feature/lesson implementation plans
CONTEXT.md          The project's own glossary — canonical definitions for its domain terms
CODING_STANDARDS.md How code here should be written — conventions not captured by an ADR or CONTEXT.md
lessons/            A parallel, self-contained teaching curriculum built alongside the real feature work
learning-records/    Notes on what's already been understood, so lessons build on real prior knowledge
```

`MISSION.md` and `NOTES.md` capture the learning goals and in-progress teaching plan in more detail, if you're
curious how the two purposes above actually get executed day to day.

## Running it on a fresh machine

Everything runs in Docker — you do **not** need Python, Node, or Postgres installed just to run the app. The
one host-side tool you need beyond Docker is `dbmate`, because database migrations are run from your machine,
not from a container.

### 1. Install the prerequisites

| Tool | Needed for | Install |
| --- | --- | --- |
| **Git** | Cloning the repo | [git-scm.com](https://git-scm.com/downloads) |
| **Docker** with **Compose v2** (`docker compose`, not `docker-compose`) | Running the whole stack | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or Docker Engine + the Compose plugin (Linux) |
| **dbmate** | Applying the SQL migrations in `db/migrations/` | `brew install dbmate` on macOS, or a binary from [dbmate's releases](https://github.com/amacneil/dbmate/releases) (CI pins `v2.35.1`) |

Docker needs to actually be running before you start. The stack includes Milvus (plus its etcd and MinIO
sidecars), which is the heavy part — if containers get killed or Milvus never turns healthy, raise Docker's
memory allocation (Docker Desktop → Settings → Resources) to around 4 GB or more.

These ports must be free on your machine: `3000` (UI), `8000` (API), `5432` (Postgres), `6379` (Redis),
`9000`/`9001` (MinIO), `19530`/`9091` (Milvus).

**Only if you want to run the test suites or the frontend dev server on your host** (not needed to run the app):
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) (which manages Python 3.12+ for you) and
Node 24 + npm.

### 2. Get API keys and configure `.env`

```bash
git clone <this repo's URL> ticker-news-analysis
cd ticker-news-analysis
cp .env.example .env
```

Then edit `.env`. Most values in `.env.example` work as-is for local development; these need your input:

| Variable | Required? | What to put there |
| --- | --- | --- |
| `FINNHUB_API_KEY` | **Yes** | Free key from [finnhub.io](https://finnhub.io) — sign up and copy it from your dashboard. Without it, news fetching from Finnhub fails. |
| `SEC_EDGAR_USER_AGENT` | **Yes** | Not a secret — a descriptive string with your app name and a contact email, e.g. `TickerNewsAnalysis you@example.com`. The SEC requires this on every EDGAR request. |
| `OPENAI_API_KEY` | Optional | Key from [platform.openai.com](https://platform.openai.com). Powers story grouping (embeddings) and headline sentiment. Costs a fraction of a cent at this project's volume. If left blank, search still works — grouping and sentiment are skipped rather than failing. |

The rest can stay at their defaults:

- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — the local Postgres container's credentials.
- `MILVUS_MINIO_ACCESS_KEY` / `MILVUS_MINIO_SECRET_KEY` — MinIO's well-known local-dev defaults (`minioadmin`).
- `DATABASE_URL` — used by `dbmate` on your host, so it points at `localhost:5432`. If you change the
  `POSTGRES_*` values above, change this to match. (The containers get their own connection string from
  `docker-compose.yml`, not from this line.)
- `TEST_DATABASE_URL` — a separate `ticker_test` database, only used by the backend test suite.

`.env` is gitignored — never commit it.

### 3. Build and start the stack

```bash
docker compose up --build -d
```

The first build takes a few minutes (it builds the React frontend, installs the Python dependencies, and pulls the
Postgres, Redis, etcd, MinIO, and Milvus images). Milvus has a ~90-second startup grace period, and the `worker`
container waits for it to be healthy, so give it a couple of minutes.

### 4. Run the database migrations

Compose doesn't run migrations, so a fresh database is empty until you do this. Run it from the repo root, once
the `db` container is up (step 3 already did that):

```bash
dbmate --no-dump-schema up
```

`dbmate` reads `DATABASE_URL` from your `.env` automatically. `--no-dump-schema` skips regenerating
`db/schema.sql` (which would otherwise need `pg_dump` installed on your host and show up as a git diff).
Re-run this command any time you pull new migrations.

### 5. Check that it works

```bash
docker compose ps                      # every service should be "running"; most show "(healthy)"
curl http://localhost:8000/api/health  # aggregate check: db, redis, worker, milvus
```

- UI: [http://localhost:3000](http://localhost:3000) — search a ticker like `AAPL`.
- API: [http://localhost:8000](http://localhost:8000) (`/api/health`, `/api/search?ticker=AAPL`)

The frontend calls the API at a hardcoded `http://localhost:8000` (`frontend/src/config.ts`), so open the UI on the
same machine that's running Docker.

### Day-to-day commands

```bash
docker compose logs -f api worker   # follow logs for the API and the background worker
docker compose down                 # stop everything, keep the data
docker compose down -v              # stop everything AND delete all data (Postgres, Milvus, etc.) — re-run step 4 after
docker compose up --build -d        # rebuild after changing backend or frontend code
```

### Optional: development setup

```bash
git config core.hooksPath .githooks   # once per clone — activates the pre-commit comment-length check
                                      # (see CODING_STANDARDS.md); needs python3 on your PATH

# Backend tests — the `db` container must be up and migrations applied (they create/migrate `ticker_test` themselves)
cd backend && uv run pytest

# Frontend: install deps, then typecheck, test, or run the hot-reloading dev server on :3000
# (stop the `ui` container first if it's running — both want port 3000)
cd frontend && npm ci
npm run typecheck && npm run test
npm run dev
```

One image runs in three modes (`ui`/`api`/`worker`, picked by `APP_MODE`) — see
`docs/adr/0001-single-image-multi-mode-containers.md` for why.

## Current state

The backend is complete for the first real feature (ticker search — see `docs/specs/0001-first-feature.md`) and
tested. The frontend is in progress, being built lesson by lesson alongside the teaching curriculum in
`lessons/`.
