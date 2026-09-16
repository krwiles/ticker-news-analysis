# Grouping's Milvus dependency is injected, not global; grouping failures are signaled through the API, not only logged

Planning lesson 20's test suite surfaced two related gaps in lesson 19's grouping code, both decided here,
before any lesson 20 code gets written.

## Decision 1: the Milvus client becomes an injectable parameter

`_match_or_create_story`, `_assign_stories`, and `ensure_story_primaries_collection` currently reach out to the
global `get_milvus_client()` internally — the one place in this grouping code that isn't parameter-injected the
way everything else already is (`session`/`session_factory` throughout `providers.py`, `client: httpx.AsyncClient`
for every provider call). Lesson 7's own plan already named why that pattern matters: *"this is the direct
payoff of `providers.py`/`search.py` taking `session_factory` as an injectable parameter: tests pass this in,
zero production code changes needed to make it testable."* The Milvus calls never got that treatment, because
lesson 19 was explicitly out of scope for dedicated tests.

Decision: all three functions gain an optional `milvus=None` parameter, defaulting to the real
`get_milvus_client()` — same shape as every other injected dependency in this module.

### Considered options

- **Monkeypatch the global singleton in tests** (rejected): works, but no other test in this suite uses
  `unittest.mock.patch` — `test_search_endpoint.py`'s `_FakeArqRedis`/`_FakeJob` and every `session_factory`
  usage are all real dependency injection, not monkeypatching. Adopting a different testing style here just for
  Milvus would be inconsistent with the rest of the codebase, and leaves the underlying DI gap in place.
- **A real test Milvus service container in CI**, same shape as the existing `postgres` service (rejected as
  the primary approach): would catch a real class of bug a fake can't (see Decision 2 below's honest
  limitation) — but standalone Milvus needs `etcd` + `minio` sidecars too, with a documented 90s healthcheck
  `start_period` (lesson 16) that would slow down every CI run substantially. Matches ADR 0008's own reasoning
  for keeping this project's CI footprint light.
- **Parameter injection + a hand-rolled in-memory fake** (chosen): a small fake with a real cosine-similarity
  `search()` (not canned responses) and an `insert()` that appends to an in-memory list — fast, CI-friendly,
  and actually exercises matching *decisions*, not just call counts. Same precedent as `_FakeArqRedis`/`_FakeJob`.

### Consequences

- A real, honest limitation, not solved here: an in-memory fake has no notion of "not yet visible" — it can't
  meaningfully regression-test Milvus's actual `consistency_level="Strong"` behavior (the class of bug lesson
  19 found live: unflushed inserts, and the flush-vs-consistency-level performance question). That's an
  infrastructure fact, not application logic, and no fake can substitute for testing it. Accepted per Decision
  3 below (keep the throwaway live-verification scripts as an occasional manual check, not deleted).
- The refactor itself must be done in isolation, verified against the full existing test suite *and* re-run
  against lesson 19's own live-verification scripts before any other lesson 20 work begins — confirming
  identical behavior, not just "tests still pass."

## Decision 2: grouping failures are signaled through the API response, not only logged

Lesson 19 shipped one inconsistency: news-matching gracefully skips when `OPENAI_API_KEY` isn't configured
(headlines still persist correctly, just left ungrouped), but if the key *is* configured and OpenAI or Milvus
is transiently unreachable mid-run, the resulting `ProviderFetchError` propagates all the way up and fails the
entire `fetch_and_persist_headlines` job — even though headlines were already safely committed before grouping
started.

Decision: both cases now degrade gracefully (news-matching is wrapped in its own failure handling, headlines
always persist regardless of grouping's outcome), **and** the distinction between them is preserved and
surfaced, not collapsed into silence:

- `_assign_stories` returns a status: `"ok"` (ran to completion, including the trivial case of nothing new to
  group), `"skipped"` (no `OPENAI_API_KEY` configured — expected, deliberate), `"error"` (configured, but a
  real failure occurred and was caught).
- `fetch_and_persist_headlines`'s result dict gains a `grouping` field carrying that status.
- `/api/search`'s JSON response includes it too — additive, so existing consumers that don't look at it are
  unaffected.
- `grouping` stays **independent** of the existing `status` field (`success` / `partial_failure` /
  `complete_failure`), which remains scoped to provider-fetch outcomes only. A grouping error is a real but
  orthogonal concern from "did EDGAR/Finnhub respond" — folding it into the same enum would conflate two
  different failure domains that can and do occur independently.

### Considered options

- **Hard-fail the whole job on any grouping error** (rejected, the status quo): simplest, but a fetch that
  genuinely succeeded (real headlines persisted) shouldn't report as failed over a downstream, non-essential
  concern.
- **Log-only, no API signal** (rejected): insufficient on its own — a real, ongoing OpenAI/Milvus outage would
  be invisible to anyone not actively tailing worker logs, and to the API consumer entirely.
- **Catch and surface distinctly** (chosen): headlines always persist; grouping's own outcome is visible
  wherever the job's result already flows, not a new, separate notification path.

### Consequences

- `/api/search`'s response shape changes ahead of lesson 21's own planned reshaping (the `today`/`recent` →
  N-day/Story restructuring) — lesson 21 must preserve or fold in this `grouping` field, not drop it while
  reshaping the rest of the response.
- The `"skipped"` vs `"error"` distinction only matters for observability and future UI messaging (lesson 22) —
  functionally, both leave the same headlines ungrouped today. Worth not losing that distinction anyway: an
  operator (or a future UI) telling "grouping isn't configured" apart from "grouping is configured but broken"
  is a real, different signal.
- **A future sentiment-analysis spec will need the identical shape of decision** — "is my external dependency
  configured, and if it is, is it currently working" — surfaced the same observable way, not solved from
  scratch. See ADR 0007's updated Consequences.
