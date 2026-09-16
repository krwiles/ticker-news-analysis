# Lesson 18 plan — OpenAI embeddings integration

Scope per `NOTES.md`: a new provider-style call in `providers.py` (same shape as EDGAR/Finnhub), get real
embeddings for real headline text, verify live. **No Milvus wiring yet** — just proves the API call works.
Mirrors lesson 16's shape: infra/capability proven in isolation before lesson 19 wires it into real logic.

## Architectural approach

`get_embedding()` lands in `providers.py`, in the exact shape ADR 0010 already committed to by name: "Every
provider function shares one shape (`client: httpx.AsyncClient` in, `ProviderFetchError` on failure, a
normalized dict out) — true of `get_company`, `fetch_edgar_filings`, `fetch_finnhub_news`, and now
`get_embedding`." Raw `httpx`, no `openai` SDK.

```python
async def get_embedding(text: str, client: httpx.AsyncClient) -> list[float]:
```

- `POST https://api.openai.com/v1/embeddings`, `Authorization: Bearer {settings.openai_api_key}`, body
  `{"model": OPENAI_EMBEDDING_MODEL, "input": text}`.
- Response: `response.json()["data"][0]["embedding"]`.
- Same try/except → `ProviderFetchError` pattern as `fetch_finnhub_news`.
- Returns a plain `list[float]` — no dataclass needed, there's only one meaningful value.

**Two decisions, confirmed with the user:**
1. **Model: `text-embedding-3-small`** (1536 dimensions) — cheapest tier, matches ADR 0007's own
   "~$0.02–0.04/month" estimate. This number is what unblocks lesson 19's Milvus collection schema:
   `milvus_client.py`'s own docstring says that schema "depends on OpenAI's embedding dimension, not chosen
   until lesson 18" — this lesson is what settles it.
2. **Input text: `title` alone when `summary` is `None`, else `f"{title}\n\n{summary}"`.** ADR 0007 said
   "`title` + `summary`, when present" but never specified the join format; this closes that gap.

## Files and components likely to change

**New**: nothing — no new files, `get_embedding()` is added to the existing `providers.py`.

**Changed**:
- `backend/src/ticker_backend/config.py` — new `openai_api_key: str = ""` setting, same shape as
  `finnhub_api_key`.
- `backend/src/ticker_backend/providers.py` — new `OPENAI_EMBEDDING_MODEL` constant + `get_embedding()`.
  `fetch_and_persist_headlines` stays untouched — no wiring this lesson.
- `docker-compose.yml` — `OPENAI_API_KEY: ${OPENAI_API_KEY}` added to the shared `&app-env` anchor, same
  precedent as `FINNHUB_API_KEY` (shared across all three containers even though only `worker` actually calls
  the function that reads it).
- `backend/tests/test_providers.py` — two new respx-mocked tests.

**Untouched**: `.env.example` (already has the `OPENAI_API_KEY=` placeholder, commit `699f88a`), `models.py`,
`search.py`, `milvus_client.py`, `worker.py`, all frontend code.

## Database / data model changes

None. No migration, no ORM model touched. `stories` / `headlines.story_id` already exist (lesson 17); this
lesson doesn't persist embeddings anywhere — that's lesson 19's Milvus insert, gated on the dimension this
lesson determines.

## API / interface changes

None to this app's own surface — no new FastAPI route, no change to `/api/search`'s response shape (lesson
21). The only new "interface" is the outbound call to OpenAI's `/v1/embeddings`.

## Backend / frontend changes

Backend only, as listed above. No frontend changes — same scope shape as lesson 16 (Milvus infra) and lesson 6
(schema). Frontend isn't touched until lesson 22.

## Existing tests / new tests required

Existing 18 backend tests (`test_providers.py`, `test_search.py`, `test_search_endpoint.py`) should keep
passing unchanged — `get_embedding` is new and additive, no existing code path calls it.

New, in `test_providers.py`, same `respx.mock` discipline as `test_finnhub_403_raises_typed_error`:
- `test_get_embedding_returns_vector` — mocks a 200 with a known `data[0].embedding` array, asserts it's
  returned as-is.
- `test_get_embedding_raises_typed_error_on_failure` — mocks a 401/500, asserts `ProviderFetchError`.

Live verification (not a committed test — matches how lessons 7/8 verified EDGAR/Finnhub live): one real call
against OpenAI's actual endpoint with a real headline's title/summary, confirming the assumed request/response
shape and checking real latency against `job_timeout_seconds`'s 10s budget (flagged by ADR 0007 as "worth
verifying live once real embedding latency exists to measure, not assumed fine in advance").

## Risks and assumptions

- Confirmed still true at planning time: `OPENAI_API_KEY` isn't wired into `config.py` or `docker-compose.yml`
  yet — added as part of this lesson.
- The live-verification step needs a real, funded OpenAI API key reachable from this machine — if unavailable,
  that one step blocks (the mocked tests can still pass independently of it).
- `milvus_client.py`'s flagged sync/blocking-gRPC concern does not apply to this lesson — `MilvusClient` isn't
  touched until lesson 19.

## Incremental steps

1. Add `openai_api_key` to `config.py`.
2. Wire `OPENAI_API_KEY` into `docker-compose.yml`'s `&app-env`.
3. Implement `get_embedding()` in `providers.py`.
4. Write the two respx-mocked tests; run the full suite, confirm 18 existing + 2 new = 20/20 green.
5. Verify live against OpenAI's real endpoint (throwaway script, not committed) — confirm the response shape
   assumption and real latency.
6. Write `lessons/0018-*.html` and this plan's "what actually happened" addendum.

## What actually happened during execution

Built exactly as planned — no deviations. `openai_api_key` added to `config.py`; `OPENAI_API_KEY` wired into
`docker-compose.yml`'s shared `&app-env`, same pattern as `FINNHUB_API_KEY`. `providers.py` gained
`OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"`, `embedding_input_text()` (a small pure helper, extracted
so the title/summary join decision is independently testable — the same reasoning `split_today_recent` already
established for pulling pure logic out of an endpoint), and `get_embedding()`.

Four new tests, not two — `embedding_input_text()`'s own pure logic picked up two direct unit tests
(no-summary / with-summary) alongside the two respx-mocked `get_embedding` tests originally planned. 22/22
total, zero regressions.

**Live verification** (real call against OpenAI, using a real headline's title + summary):
- Dimensions: **1536**, confirming `text-embedding-3-small`'s documented size.
- Response shape matched the assumption in this plan exactly (`data[0].embedding`) — no correction needed.
- Latency: **2.23s**, well inside `job_timeout_seconds`'s 10s budget. Closes ADR 0007's own flagged
  uncertainty ("worth verifying live once real embedding latency exists to measure, not assumed fine in
  advance") — at this single-call scale, latency is not a concern. Worth re-checking once lesson 19 calls this
  inside the real fetch job's `asyncio.gather`, alongside EDGAR/Finnhub, rather than in isolation.

`fetch_and_persist_headlines` and `milvus_client.py` both remain untouched, exactly as scoped — lesson 19 is
where this gets wired into the real matching flow.

## Revised after initial build: batched, not one call per headline

The "worth re-checking" flag above got checked immediately, not deferred to lesson 19: the single-call latency
(2.23s) made the real risk concrete on its own — a search turning up tens of headlines, each embedded serially,
would blow `job_timeout_seconds`'s 10s budget on embeddings alone. `get_embedding(text, client) -> list[float]`
was replaced with `get_embeddings(texts: list[str], client) -> list[list[float]]`, using OpenAI's native array
`input` support (one request for a whole batch, not one per item). Each returned vector is placed by its own
`index` field rather than trusted to preserve array order.

Live-verified against 10 realistic headlines: **1.13s** for the full batch — *faster* than the 1.83s
single-headline baseline measured in the same run, and nowhere near the naive serial estimate of ~18.32s for
the same 10 calls run one at a time. Confirms the premise: batch latency is flat against batch size, not
linear, because the dominant cost is the network round-trip rather than per-item compute.

Tests were revised, not just added to: the original two `get_embedding` tests became
`test_get_embeddings_places_vectors_by_index_not_array_order` (response items deliberately returned out of
index order, proving the placement logic is real — same "insert out of order" discipline as
`test_story_primary_is_derived_as_earliest_published_headline`) and
`test_get_embeddings_raises_typed_error_on_failure`, plus a new
`test_get_embeddings_empty_list_skips_the_network_call` (no respx mock registered at all — proves the
empty-input guard actually skips the call rather than just returning early after making one). 23/23 total.

ADR 0007's Consequences and ADR 0010's Consequences were both updated in place to reflect the batched shape —
same precedent as ADR 0009's in-place revision after lesson 17's circular-FK simplification. `lessons/0018-*.html`
was rewritten to tell the real version-one/version-two story rather than presenting the batched version as if
it were the only one ever built.
