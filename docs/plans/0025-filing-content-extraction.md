# Lesson 25 plan — filing content extraction

Scope per `NOTES.md`: given a raw filing URL, extract its most sentiment-relevant content, capped at a
size limit. Substantial, real-world HTML-parsing work — mirrors lesson 19's dedicated treatment of "the
actual grouping logic," not a small add-on to an existing function.

## The central design change, made during planning, before any code

ADR 0014 originally proposed a three-tier strategy, tier 1 being structural (anchor-based) extraction. That
tier was dropped during this lesson's own planning, based on real evidence, not a guess:

- The original "match on anchor id, not label text" guidance (from fixing Microsoft) was never rechecked
  against Apple, whose anchor ids are opaque — it would have silently broken the very first filer this
  investigation started with.
- A broader sample (5 more real filers) found a third, more serious failure mode: Western Digital's TOC
  links wrap only the page number, not the item label — a structural gap a regex can't reach, needing a
  real DOM parser (`lxml`/`BeautifulSoup`, neither a current dependency) to fix.
- Only 2/5 of that broader sample matched via either combined heuristic. Not reliable enough to build.

**What replaced it, validated against 12 real, diverse filers**: plain-text heading search (`Item 7`,
requiring the real title "Management" to follow — a bare number alone matched stray citations twice),
extracting through the next real heading (`Item 7A`/`Item 8`, same "real title must follow" discipline), a
reference-check for the one real case (Friedman Industries) where the heading exists but the actual content
doesn't, and blind truncation from the document's start as the final fallback — covering both the
reference-only case and any filing type that doesn't use this numbering at all (8-K/S-1/DEF 14A).

**Character-based cap, confirmed with the user** — `FILING_CONTENT_CAP_CHARS = 80,000` (≈20,000 tokens,
ADR 0014's chars/4 approximation), no real tokenizer dependency.

## What gets built

**`backend/src/ticker_backend/providers.py`**, three new functions:
- `_strip_html_to_text(html) -> str` — tag/entity stripping, the same regex approach already proven across
  all 12 real filers during planning.
- `_extract_relevant_filing_section(text) -> str` — the heading-search/reference-check/truncate logic, pure
  and independently testable, mirroring `embedding_input_text`'s own "small pure helper" precedent.
- `async def get_filing_content(url, client) -> str` — fetches the real document, delegates to the two
  helpers above, logs on actual truncation.

## Files and components likely to require changes

Same as above — `providers.py` only. `backend/tests/test_providers.py` gains new tests. No other file.

## Database / data model changes

None.

## API / interface changes

None.

## Backend / frontend changes

Backend only. No frontend changes.

## Existing tests / new tests required

Real full 10-Ks are too large to embed as literal fixtures (50,000-100,000+ tokens). New tests use small
synthetic HTML **modeled on the real structure found live across 12 filers** (documented as such, not a
literal capture), covering the three real scenarios: heading found with real content (stops at the next
heading), heading found but reference-only (falls back to document start), no heading at all (mirrors an
8-K). Plus cap-enforcement and the two `_strip_html_to_text` cases.

## Risks and assumptions

- The heading-search pattern is tuned specifically to 10-K/10-Q's "Item 7" — acceptable, since only those
  two filing types have this section at all; everything else falls through to blind truncation naturally.
- The reference-check pattern was validated against exactly one true-positive case (Friedman Industries) at
  planning time — asked the user for a broader check before trusting it; gathered 4 more real small-cap
  filers (Chase General, US Global Investors, Biomerica, Twin Disc), all with real inline MD&A content, all
  correctly not triggering the check. 11 correct negatives + 1 correct positive, now.

## Incremental steps

1. Implement `_strip_html_to_text` + tests.
2. Implement `_extract_relevant_filing_section` + tests (three scenarios + cap enforcement).
3. Implement `get_filing_content` + tests.
4. Run the full suite.
5. Live-verify against real URLs already gathered during planning.
6. Revise ADR 0014 in place to replace the stale three-tier description.
7. Write `lessons/0025-*.html` and this addendum.

## What actually happened during execution

A second real instance of the exact same bug class the planning phase already found once, this time caught
during implementation, not planning. The *next*-heading pattern originally proposed (`Item 7A` / `Item 8`,
bare) had the identical specificity problem the `Item 7` heading pattern was already fixed for — and it
showed up immediately on live verification: Apple's own real MD&A opening sentence contains an inline
cross-reference ("...notes included in Part II, **Item 8** of this Form 10-K...") that matched as the
section boundary, cutting the extraction to 236 characters instead of ~18,000.

Fixed the same way the first instance was: require the real, SEC-standardized titles ("Quantitative"/
"Financial") to follow the item number, not just the bare number. Re-verified live against Apple, Friedman
Industries, George Risk Industries, and Western Digital — all four now match the exact measurements found
during planning (4,497 / 7,752 / 4,616 / 10,720 tokens respectively). Not caught by the synthetic test
fixtures (which used realistic-but-simplified text with no inline cross-references) — only surfaced by
testing against a real document. A second, similar case worth naming explicitly for future lessons: a test
suite built entirely from synthetic fixtures can miss a failure mode a real document happens to contain,
even when the fixtures are modeled on real structure.

56/56 tests (8 new), zero regressions. ADR 0014 revised in place (same precedent as ADR 0009/0011) to
replace the stale three-tier description with the real two-tier design and both specificity bugs found along
the way.
