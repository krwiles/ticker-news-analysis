# Lesson 16 plan — Milvus, standalone (Arc 4, spec 0002)

Scope per `NOTES.md`: docker-compose wiring for standalone Milvus (`etcd` + `MinIO` sidecars), a real
collection, basic insert/search via `pymilvus` — **no app logic yet**. Walking-skeleton shaped, mirroring
lesson 1 (prove the container talks before business logic exists) and lesson 6 (schema/infra lesson before the
logic that uses it).

## Architectural approach

Fetched the real, current standalone reference config directly (`milvus-io/milvus`'s own `deployments/docker/
standalone/docker-compose.yml`) rather than approximate it — three services: `etcd`, `minio`, `standalone`/
`milvus`. Two deliberate deviations from copying it verbatim: named Docker volumes instead of the reference's
bind-mounts (matching this project's own `db-data` convention), and no separate `networks:` block (the
reference declares one because it's a standalone file with nothing else in it; here, the new services join the
same default network everything else already shares).

**Where the Python side lives**: a new `backend/src/ticker_backend/milvus_client.py`, deliberately thin — just
connection setup, mirroring `db.py`'s `engine` pattern. No collection schema for real headline embeddings gets
created here — that depends on OpenAI's embedding dimension, not chosen until lesson 18. Verification uses a
throwaway/generic test collection purely to prove the client/connection/insert/search mechanics work.

## Files and components likely to change

**New**: `backend/src/ticker_backend/milvus_client.py` — connection setup only.

**Changed**: `docker-compose.yml` (three new services, three new named volumes, `worker`'s `depends_on` gains
`milvus`), `backend/pyproject.toml`/`uv.lock` (adds `pymilvus`), `.env`/`.env.example` (MinIO credentials as
env vars, defaulting to the well-known local-dev default), `backend/src/ticker_backend/config.py` (a new
`milvus_uri` setting, same shape as `redis_url`).

**Untouched**: `providers.py`, `models.py`, `search.py`, all frontend code, all existing tests.

## Database / data model changes

None in Postgres. No Milvus collection schema for real headline data yet either.

## API / interface changes

None — this lesson touches no HTTP-facing behavior at all.

## Backend / frontend changes

Backend only, as listed above. No frontend changes.

## Existing tests / new tests required

No new tests, deliberately — same precedent ADR 0005 already set for lessons 1 and 4: infra-proving lessons
with no business logic get verified live, not unit-tested. `milvus_client.py` is a thin connection helper with
nothing meaningfully assertable beyond "does it connect," which live verification (a real insert/search
against the real running container) proves more convincingly than a mock could.

## Risks and assumptions

- Apple Silicon + `etcd` — a historical rough edge flagged in earlier research, not yet verified against this
  actual machine before this lesson.
- Resource footprint — Milvus' own docs recommend 8GB+ RAM for standalone, on top of everything else already
  running.
- No port collisions identified (`19530`/`9091`/`9000`/`9001` all clear of this project's existing ports).
- `pymilvus` needs no special version-pin treatment, unlike `dbmate` in lesson 15 — it's a normal Python
  dependency captured in `uv.lock`.

## Incremental steps

1. Add `etcd`/`minio`/`milvus` services to `docker-compose.yml`, bring them up standalone, verify healthy.
2. Add `pymilvus` to `backend/pyproject.toml`, add `milvus_uri` to `config.py`.
3. `milvus_client.py` — connection setup only.
4. Live verification: create a throwaway test collection, insert vectors, search, confirm real results, drop
   the collection.
5. Wire `worker`'s `depends_on` to include `milvus: condition: service_healthy`.
6. Full stack sanity check: confirm `api`/`ui`/`worker` still start and `/api/health`/a real search still work.

## What actually happened during execution (deviations from the plan above, both found live)

1. **Step 1 broke immediately**: `docker compose pull` failed on the exact reference tag —
   `pull access denied for minio/minio`. MinIO archived its OSS edition and pulled `minio/minio` from Docker
   Hub entirely (~Oct 2025, fully gone as of this week). Fixed by switching to `quay.io/minio/minio` at the
   same tag, verified by pulling it directly before editing the compose file, then cross-checked against
   `milvus-io/milvus` issue #53430 (the Milvus maintainers hit the identical problem).
2. **Step 4 initially returned zero search results** despite a successful insert. Root-caused via
   `get_collection_stats()`: `insert()` doesn't make data searchable until explicitly `flush()`ed — row count
   stayed 0 post-insert, became 1 only after flushing. Re-ran the proof with an explicit `flush()` call;
   correctly found the near-duplicate vector and excluded the dissimilar one. Flagged explicitly for lesson 19,
   not solved here: a new Story's primary embedding needs `flush()` somewhere in the real matching flow.
3. **`depends_on` structure changed from the plan's literal wording** ("worker's depends_on gains a milvus
   entry") to something more precise once actually building it: extracted a new `&app-depends-on` anchor
   (mirroring how `environment` already has `&app-env`) so `worker` can merge the shared `db`/`redis`
   dependency and add `milvus`, while `api`/`ui` keep depending on the unmodified shared anchor. Deliberate,
   not shared like `db`/`redis` are — Milvus' 90s healthcheck `start_period` would otherwise slow down
   `api`/`ui` startup for a dependency they'll never use. Verified live: `api`/`ui` started as soon as
   `db`/`redis` were healthy; `worker` visibly waited on `milvus` too.

Full stack sanity check (step 6) passed: `/api/health` and a real `/api/search?ticker=AAPL` both worked
correctly after everything above was wired in.
