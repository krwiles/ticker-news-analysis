# Lesson 24 plan — OpenAI sentiment classification call

Scope per `NOTES.md`: a new provider-style call in `providers.py` (same shape as EDGAR/Finnhub/embeddings),
get a real score/gloss/rationale for real headline text, verify live. **No filing content, no job wiring, no
Story aggregate yet** — mirrors lesson 18's own scope discipline exactly.

## Architectural approach

`get_sentiment()` lands in `providers.py`, the same shared shape every provider function already uses
(`client: httpx.AsyncClient` in, `ProviderFetchError` on failure). A real architectural difference from
`get_embeddings`, worth stating plainly: Chat Completions has no native array-input batching the way the
embeddings endpoint does — each call is one conversation, one response. So `get_sentiment` is single-item by
design; concurrency across many headlines happens via `asyncio.gather` at the call site (lesson 26), not
inside this function.

```python
async def get_sentiment(text: str, client: httpx.AsyncClient) -> dict:
```

- `POST https://api.openai.com/v1/chat/completions`, Structured Outputs (`response_format:
  {"type": "json_schema", ...}`) guaranteeing `{"score": int, "gloss": str, "rationale": str}` back, rather
  than parsing free text.
- Reuses `embedding_input_text()` directly for the news-headline input — confirmed with the user rather than
  writing a near-duplicate `sentiment_input_text`, since the join logic (title alone, or `title\n\nsummary`)
  is currently identical for both callers.
- Same try/except → `ProviderFetchError` pattern as every other provider function.

**Two things verified live during planning, not assumed from ADR 0014:**
1. **Model: still `gpt-5-nano`** — re-checked against OpenAI's real pricing page; no change since ADR 0014's
   own research.
2. **The score-to-enum threshold cutoffs are deferred to lesson 26**, not decided here — `NOTES.md`'s rough
   sketch originally attached this to lesson 24, but the closer precedent (lesson 18 proved the embeddings
   call works; lesson 19, once the call was actually wired into real matching logic, is where
   `story_similarity_threshold` got tuned against real data) argues for the same split here. Confirmed with
   the user before building.

**One real design problem found and fixed during planning, not left as a gotcha**: a naive prompt's `gloss`
came back as `"Positive"` — a bare restatement of the enum, exactly what spec 0005's Success Criteria forbid.
Fixed with an explicit system-prompt instruction against restating the enum; reverified live across three
different real-ish cases (`bullish`/90, `concerning`/30, `routine`/50) before writing the real function.

## Files and components likely to change

**Changed**:
- `backend/src/ticker_backend/providers.py` — new `OPENAI_SENTIMENT_MODEL` constant, the Structured Outputs
  schema/prompt constants, and `get_sentiment()`. `fetch_and_persist_headlines` stays untouched — no wiring
  this lesson.
- `backend/tests/test_providers.py` — two new respx-mocked tests, mirroring `get_embeddings`' own test set.

**Untouched**: `models.py` (lesson 23 already added the columns this will eventually fill), `search.py`,
`worker.py`, all frontend code, `config.py` (no new setting — the model name is a bare `providers.py`
constant, matching `OPENAI_EMBEDDING_MODEL`'s own precedent, not a `Settings` field).

## Database / data model changes

None. This lesson doesn't persist anything — lesson 23's columns stay unfilled until lesson 26 wires this
call into the real job.

## API / interface changes

None. `/api/search`'s response is untouched until lesson 28.

## Backend / frontend changes

Backend only, as listed above. No frontend changes until lesson 29.

## Existing tests / new tests required

Existing 46 backend tests should keep passing unchanged — `get_sentiment` is new and additive, no existing
code path calls it.

New, in `test_providers.py`, same `respx.mock` discipline as `get_embeddings`' own tests:
- `test_get_sentiment_returns_structured_score_gloss_rationale` — mocks a 200 with a real
  Structured-Outputs-shaped `choices[0].message.content` JSON string, asserts it parses to the expected dict.
- `test_get_sentiment_raises_typed_error_on_failure` — mocks a 401, asserts `ProviderFetchError`.

No equivalent of `get_embeddings`' "empty list skips the network call" test — there's no list here to be
empty; the natural analog (not calling this function at all for zero headlines) lives at the call site in
lesson 26, not in this single-item function.

Live verification (not a committed test, same as lesson 18's own script): real calls against OpenAI's actual
endpoint across a small spread of genuinely different real-ish headlines, confirming the response shape and
that the gloss-restatement fix actually holds.

## Risks and assumptions

- Structured Outputs' documented model-support surface for `gpt-5-nano` specifically is ambiguous in
  OpenAI's own docs (a fetch during planning surfaced confusing/possibly-stale references to a different API
  and an unfamiliar model name) — resolved by testing the real thing directly rather than trusting the docs
  summary; if OpenAI ever changes this without an announcement, that's a real if currently low risk.
- `providers.py` had the exact same `pymilvus`-import-order landmine `health.py` was fixed for during spec
  0003 (`from pymilvus import MilvusException` before `ticker_backend.config` is imported) — never exposed
  until a script imported this module standalone. Found live while trying to verify `get_sentiment`, fixed
  the same way `health.py` was.

## Incremental steps

1. Implement `get_sentiment()` + its constants in `providers.py`.
2. Write the two respx-mocked tests; run the full suite, confirm 46 existing + 2 new = 48/48 green.
3. Verify live against OpenAI's real endpoint (throwaway script, not committed) across a small spread of
   real-ish cases.
4. Write `lessons/0024-*.html` and this plan's "what actually happened" addendum.

## What actually happened during execution

Built close to plan, with two real things found live along the way — neither anticipated in the plan above
until they were actually hit.

**Found and fixed: the `pymilvus` import-order landmine, again.** The first attempt at live verification (a
standalone script doing `from ticker_backend.providers import get_sentiment`) failed with the exact same
`NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres` spec 0003's own investigation diagnosed
in `health.py` — `providers.py` had the identical ordering bug (`from pymilvus import MilvusException` before
`from ticker_backend.config import settings`), just never exposed because every existing test file that
touches `providers.py` also imports `ticker_backend.config` earlier in the same file, by coincidence of
import order, not by design. Fixed the same way: reordered the import, added a comment explaining why the
order is load-bearing so a future edit doesn't silently reintroduce it.

**A second real finding, transient, not a bug**: the live-verification script's first run hit an
`httpx.ReadTimeout` — httpx's own default client timeout is 5 seconds, and the throwaway script never set
one explicitly. Checked the real job's own client construction (`providers.py`): both existing
`httpx.AsyncClient(...)` call sites already use `timeout=10.0`, comfortably covering the 1.8-3.4s per-call
latency already measured live in ADR 0014's own research. Not a real risk to the actual feature — purely an
artifact of the throwaway script not matching the real app's own client configuration.

48/48 tests, zero regressions. Live verification (real API, `timeout=30` on the script's own client)
confirmed the implemented function end-to-end:

- `"Apple beats earnings expectations."` → `{score: 97, gloss: "bullish", rationale: "..."}`
- `"Company X reports layoffs."` → `{score: 28, gloss: "concerning", rationale: "..."}`
- `"Company Y schedules annual shareholder meeting."` → `{score: 50, gloss: "routine", rationale: "..."}`

No enum-restating gloss in any of the three — the planning-time prompt fix held up against the real,
implemented function, not just the ad hoc script that first found the problem.
