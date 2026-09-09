# Lesson 6 plan — the `Headline` model + migration

Scope: `NOTES.md`'s lesson 6. Unlike lesson 7 onward, the underlying code here was already built during the
interrupted session — this plan covers what's left to actually call the lesson complete, not a fresh build.

## What's already done (built and reviewed)

- `db/migrations/20260909125433_create_headlines.sql` — applied, creates `headlines` (id, ticker, title, url,
  category, provider, raw_content, published_at, fetched_at) with a unique index on `url` and an index on
  `(ticker, published_at)`.
- `backend/src/ticker_backend/db.py` — shared async engine, `async_session_factory`, `Base`.
- `backend/src/ticker_backend/models.py` — the `Headline` mapped class.
- Verified live: real insert/query round trip (server-generated `id`/`fetched_at` confirmed), and the
  `category` `CHECK` constraint confirmed to reject an invalid value at the database level, not just in Python.
- Reviewed explicitly in the post-interruption discussion (Topic 1) — kept as-is on its merits, not just
  because it already existed.

Nothing above needs rebuilding. Re-verifying it from scratch would be redundant with what already happened.

## What's actually left to complete lesson 6

**1. The `health.py`/`db.py` engine consolidation** (Topic 2's decision, not yet executed): `health.py`
currently creates its own separate `create_async_engine(...)` instead of importing the one `db.py` now
provides. Small, mechanical, behavior-preserving change — `health.py` imports `engine` from `db.py`, drops its
own. Doing this now (while `db.py` is the thing lesson 6 introduces) closes that loop cleanly rather than
leaving it dangling indefinitely.

**2. The actual lesson content** — `lessons/0006-headline-model-and-migration.html`, matching the format of
lessons 1–5 (`assets/lesson.css`, eyebrow/title/subtitle, `Check your understanding`, primary sources, nav).
Proposed content outline:

- **Why `dbmate`, not Alembic** — plain SQL migrations vs. Python-generated ones; ties to the insider stack
  list explicitly naming `dbmate`.
- **Two different `DATABASE_URL`s, on purpose** — `dbmate`'s plain `postgres://` (host-side) vs. the app's
  `postgresql+asyncpg://` (container-side, set directly in `docker-compose.yml`'s `environment:`, never reading
  `.env`'s copy). A real, easy-to-miss gotcha worth naming explicitly, same spirit as lesson 5's `.env` section.
- **SQLAlchemy 2.0's `Mapped`/`mapped_column` style** — shown directly against the real `Headline` class.
- **Why a server-generated UUID** (`server_default=text("gen_random_uuid()")`) instead of generating it in
  Python — the database is the single source of truth for identity, and it's free on Postgres 13+.
- **The `category` `CHECK` constraint vs. a native Postgres enum** — ties back to the `CONTEXT.md` naming
  decision (`category`, not `kind`/`type`) and explains the tradeoff (easier to evolve later than an enum type,
  at the cost of the check living outside Python's type system — mitigated by the `Literal["news","filing"]`
  type hint on the model, shown side by side).
- **The unique index on `url` as the real dedup mechanism** — forward-references ADR 0003/0004 without
  re-explaining them.
- **Verification, shown as real output** — the actual insert/query round trip and the `CheckViolationError`
  from the earlier session, presented the way lesson 3 shows real log output rather than a hypothetical.
- **Check your understanding** — 2 questions, matching the existing lessons' density (e.g.: "why does the
  `category` check fail at the database level even though the column is just `TEXT`?"; "why is `fetched_at`'s
  default set in SQL, not in the Python model?").

## Verification for the consolidation step

Re-run the same live insert/query check from before, but afterward also hit `/health` and confirm it still
reports `db: ok` — proving `health.py`'s `SELECT 1` still works after switching to the shared engine, not just
that the switch compiles.

## Open items

- None outstanding — this lesson's content is fully known already (unlike lesson 7, nothing here depends on an
  external API's real response shape).
