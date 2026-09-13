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
lessons/            A parallel, self-contained teaching curriculum built alongside the real feature work
learning-records/    Notes on what's already been understood, so lessons build on real prior knowledge
```

`MISSION.md` and `NOTES.md` capture the learning goals and in-progress teaching plan in more detail, if you're
curious how the two purposes above actually get executed day to day.

## Running it locally

```bash
cp .env.example .env   # fill in FINNHUB_API_KEY (free tier) and SEC_EDGAR_USER_AGENT
docker compose up --build -d
```

- UI: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000) (`/api/health`, `/api/search?ticker=AAPL`)

One image runs in three modes (`ui`/`api`/`worker`, picked by `APP_MODE`) — see
`docs/adr/0001-single-image-multi-mode-containers.md` for why.

## Current state

The backend is complete for the first real feature (ticker search — see `docs/specs/0001-first-feature.md`) and
tested. The frontend is in progress, being built lesson by lesson alongside the teaching curriculum in
`lessons/`.
