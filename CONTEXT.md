# Ticker News Analysis

A tool for gathering and surfacing news and SEC filings about publicly-traded companies, searchable by ticker
symbol.

## Language

**Ticker**:
The stock symbol representing a company (e.g. `AAPL`, `MSFT`). The unit a user searches by, and the identity a
Company is looked up and stored by.
_Avoid_: Symbol, Stock

**Company**:
The persisted record a Ticker identifies: its CIK (SEC's permanent company identifier, looked up once and
cached rather than re-fetched on every search) and its name, both nullable — populated when SEC's own ticker
mapping recognizes the symbol, left null when it doesn't (e.g. a foreign issuer Finnhub covers but SEC's
US-filer mapping has no record of). A null CIK/name isn't a broken or fake row — it only exists at all once a
real Headline needed it, so its presence already means at least one provider confirmed the ticker is real. May
grow more fields later as the product does.
_Avoid_: Ticker (Ticker is the symbol/search unit; Company is the row it identifies — related, not the same
concept)

**Provider**:
The API/integration used to fetch a Headline — a technical fact about *how* a row got into the system, always
one of a small, known set (e.g. SEC EDGAR, Finnhub). Distinct from Outlet: a Provider can aggregate content
originally published by many different outlets.
_Avoid_: Publisher, Source (this is about the integration, not who wrote the content — see Outlet)

**Outlet**:
The original publisher of a Headline's content, as reported by its Provider (e.g. Yahoo, Business Insider) —
what a reader actually cares about ("via Yahoo" means something; "via Finnhub" doesn't). Not every Provider
reports one: SEC EDGAR *is* the authoritative outlet for a filing, so Outlet is typically absent there, not a
separate value.
_Avoid_: Source (retired — see Headline's _Avoid_ below), Publisher (that's Provider's avoided synonym; don't
reuse it here either — Outlet and Provider must stay visibly distinct terms)

**Headline**:
The single record for one piece of tracked news content about a Ticker: its title, its direct URL, a short
`summary` (a blurb the Provider gives us directly, shown under the headline in the UI), its `outlet` (see
Outlet — often absent), its raw content (the full article/filing body — distinct from `summary`, fetched later
by following the URL, not populated in the first pass of this feature), a `category` (`news` or `filing`), when
it was published, and — eventually — a computed `sentiment` (`positive`/`neutral`/`negative`, plus a one-word
gloss and a one-sentence summary).
_Avoid_: Source, Article (an example of the `news` category, not a synonym for the whole concept)
_Category values_: `news`, `filing` — _Avoid (field name)_: kind, type
_Sentiment values_: `positive`, `neutral`, `negative` — _Avoid_: "sentiment category" (collides with `category` above)
_Summary vs. raw content_: `summary` is a short blurb, always cheap/free from the Provider; raw content is the
full body, fetched separately and not yet built — don't conflate the two under one field.

**Today** (as used to group Headlines):
The current calendar day in US Eastern time — the stock market's trading day — not UTC and not the viewer's
local timezone. This is a tool about US-market news, so "today" anchors to the market's day regardless of where
it's viewed from. Computed fresh whenever Headlines are grouped, never stored.
_Avoid_: "today" meaning UTC or the browser's local timezone

**Story**:
The real-world event two or more same-day, same-ticker Headlines can describe in common — detected via
embedding similarity (Milvus), not text/URL matching. A grouping *over* Headlines, not a replacement for the
concept: a Headline still means exactly what its entry above says; a Story sits one level above it. Every
Headline belongs to exactly one Story, even one with no near-duplicates (a "story of one"). A Story's primary
Headline — its earliest-published member, fixed permanently once set — is what's shown as the Story's face in
the UI and what later same-day candidates are compared against; other members appear only via an expandable
list. Filing-category Headlines never participate in grouping — always a Story of one, by construction.
Grouping never spans two calendar days or two tickers.
_Avoid_: "Group" as the noun — the `Today` entry above already uses "grouped" as a plain verb for the
unrelated day-bucketing concept; reusing "Group" here risks exactly the collision that entry's own _Avoid_ is
meant to prevent elsewhere.
