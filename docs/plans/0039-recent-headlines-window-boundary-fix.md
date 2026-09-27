# Fix: RECENT_HEADLINES_WINDOW's exact-timestamp cutoff vs. Finnhub's day-granularity fetch

Not a planned lesson, no spec/ADR (implementation detail, same shape as lessons 34/35/36's own bug
fixes). Picks up the 2026-09-23 idea from `NOTES.md`: a real, already-confirmed correctness bug, chosen
next off the Roadmap's Phase 1 list.

## The mechanism, confirmed by reading the actual code (not re-guessed from the idea's own text)

Three call sites (`search.py`, `sentiment.py`, `jobs.py`) each independently compute the same cutoff:

```python
cutoff = datetime.now(timezone.utc) - RECENT_HEADLINES_WINDOW  # an exact instant, 7 days ago right now
```

`sentiment.py`'s `_fetch_pending_headlines` uses this cutoff to decide which headlines are even
*eligible* for sentiment scoring at all (`Headline.published_at >= cutoff`). Meanwhile,
`providers.py`'s `fetch_finnhub_news` asks Finnhub for a **day-granularity** range:

```python
to_date = datetime.now(timezone.utc).date()
from_date = to_date - timedelta(days=7)  # a calendar date, not an instant
```

Finnhub returns everything published on `from_date`'s *whole calendar day* — including headlines
published hours before the exact instant `now - 7 days` represents. A headline published at, say,
`2026-09-20T00:05:00Z` gets fetched and persisted just fine (Finnhub's own range includes all of
9/20). But by the time `_fetch_pending_headlines` runs its own query — even just seconds later — the
exact-instant cutoff has already moved past `2026-09-20T00:05:00Z` if "now" is anywhere after
`2026-09-27T00:05:00Z`. The headline is silently excluded from ever being scored: `sentiment_status`
stays `NULL` forever, and since only `sentiment_status = 'ok'` counts toward a Story's aggregate
(`Story.record_sentiment`, spec 0005), that Story's aggregate is permanently missing this member's
score. Time only moves forward, so a headline that misses this window once misses it every time after —
there's no later request where it becomes eligible again.

Confirmed live on 2026-09-23 (recorded in `NOTES.md`): 12 of 114 real Stories for a freshly-fetched
ticker showed a permanently-zero aggregate this way — a distinct, unrelated bug from plan 0036's own race
(that one was independently verified fixed: zero headlines had `sentiment_status = 'ok'` with
`story_id IS NULL`).

`providers.py`'s own EDGAR fetch filter (`_fetch_edgar_filings`) already uses an exact-instant cutoff
matching `RECENT_HEADLINES_WINDOW`'s original semantics, so EDGAR filings were never affected — this is
specifically a Finnhub-sourced-headline bug.

## Fix

Widen the three downstream cutoffs (`search.py`, `sentiment.py`, `jobs.py`) to align with the start of the
oldest included **UTC calendar day**, not an exact instant — a strict superset of what an exact-instant
cutoff would include, so no headline that Finnhub could have fetched for that day can ever fall outside
it. New shared helper in `config.py`, next to `RECENT_HEADLINES_WINDOW` itself (same "lives here so
neither `search.py` nor `providers.py` has to import from the other" reasoning that constant already
uses):

```python
def recent_headlines_cutoff(now: datetime) -> datetime:
    """The earliest published_at a headline can have and still count as "recent" -- aligned to the
    start of the oldest included UTC day, not an exact instant, so it can never fall inside the
    same-day granularity gap Finnhub's own from/to date range fetches by (providers.py). `now` is a
    parameter, not datetime.now() called internally, matching build_daily_view's own testable-purity
    style (search.py)."""
    oldest_day = (now - RECENT_HEADLINES_WINDOW).date()
    return datetime.combine(oldest_day, time.min, tzinfo=timezone.utc)
```

Each of the three call sites changes from:

```python
cutoff = datetime.now(timezone.utc) - RECENT_HEADLINES_WINDOW
```

to:

```python
cutoff = recent_headlines_cutoff(datetime.now(timezone.utc))
```

**No change needed to `providers.py`** — EDGAR's own fetch-side filter and Finnhub's own from/to range
are both about what gets *fetched*, not what gets *shown/scored later*; widening only the downstream
cutoff to a day boundary already covers everything either provider could have fetched for that oldest
day, EDGAR included (a day-boundary cutoff is strictly earlier than an exact-instant one, so it's a
superset, never a regression for EDGAR's own already-correct behavior).

**Accepted, not fixed further**: this widens the effective window slightly (up to just under 24 extra
hours, on the oldest day only) rather than shrinking it — the same "accepting the small edge window"
option `NOTES.md`'s original idea named, just applied as the *safe* direction (a few extra hours of a
correctly-scored headline showing up, rather than one that's silently unscorable forever).

## Files changed

- `backend/src/ticker_backend/config.py` — new `recent_headlines_cutoff(now)` function.
- `backend/src/ticker_backend/search.py`, `sentiment.py`, `jobs.py` — the one-line cutoff computation at
  each of the three existing call sites.
- New `backend/tests/test_config.py` — `derive_sentiment_enum`'s tests currently live in
  `test_providers.py` (a leftover from before lesson 28 moved that function out of `providers.py`, per
  `NOTES.md`), which is where the next config.py test would naturally end up too if left alone; starting
  a properly-named home now rather than perpetuating that.

**Untouched**: `providers.py` (confirmed above — no change needed there).

## Tests

`test_config.py`:
- `recent_headlines_cutoff` returns UTC midnight of the day exactly `RECENT_HEADLINES_WINDOW` days before
  `now`'s date, not `now - RECENT_HEADLINES_WINDOW` itself — the core behavior change.
- **The actual regression case**: given a `now` several hours into the 8th day, a headline published
  earlier that same day but *before* `now - RECENT_HEADLINES_WINDOW`'s exact instant is `>= cutoff`
  (included) — this is exactly the case that was silently excluded before the fix; asserting it directly
  is worth more here than a generic boundary check.
- A headline from the day *before* the oldest included day is still correctly excluded (the fix widens
  the window by at most a day, not unboundedly).

No changes needed to `test_search_endpoint.py`/`test_sentiment.py`/`test_jobs.py`'s existing tests — none
of them assert on the exact cutoff boundary today (confirmed by grep before writing this plan), so there's
nothing there to break.

## Verification

1. Full backend suite green, plus the new `test_config.py` cases.
2. Live-verified against the real dev database: find (or construct) a real headline whose `published_at`
   sits in the gap this bug describes, confirm its `sentiment_status` is still `NULL` under the old logic,
   then confirm a real `/api/search` call resolves it once the fix is deployed.

## What actually happened during execution

Built exactly as planned — the mechanism confirmed by reading `sentiment.py`/`providers.py` directly matched
the original 2026-09-23 idea's description, so there was nothing to re-scope once the code was actually
read. TDD followed throughout: `test_config.py` written and confirmed failing (module import error) before
`recent_headlines_cutoff` existed; a deliberate-break check afterward (reverted the function back to the old
`now - RECENT_HEADLINES_WINDOW` exact-instant logic) confirmed the two regression-relevant tests fail for
exactly the described reason before reverting the break — proof the tests are meaningful, not just green by
accident.

106/106 backend tests (3 new), zero regressions.

**Live-verified against the real running stack** with a synthetic headline (not a naturally-occurring one —
none happened to be sitting in the gap at the moment this was fixed): inserted a real `TESTGAP` headline with
`published_at` set to 02:00 UTC on the oldest included day (confirmed via direct SQL to be excluded by the old
exact-instant cutoff and included by the new day-aligned one), then called the actual deployed
`_fetch_pending_headlines` and `_load_search_results` functions directly inside the running `api` container —
both correctly picked it up. Synthetic data cleaned up afterward. A real `/api/search?ticker=AAPL` call
confirmed existing functionality is unaffected (`success`/`ok`, 9 days).

No change needed to `providers.py`, confirmed rather than assumed — EDGAR's own fetch-side filter already used
an exact-instant cutoff matching the pre-fix semantics, and a day-aligned downstream cutoff is a strict
superset of that, never a regression for EDGAR-sourced headlines.
