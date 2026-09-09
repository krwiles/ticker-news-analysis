# Ticker News Analysis

A tool for gathering and surfacing news and SEC filings about publicly-traded companies, searchable by ticker
symbol.

## Language

**Ticker**:
The stock symbol representing a company (e.g. `AAPL`, `MSFT`). The unit a user searches by.
_Avoid_: Symbol, Stock

**Provider**:
The outlet or platform a Headline is fetched from (e.g. Reuters, SEC EDGAR, a specific scraper target). One
Provider produces many Headlines over time.
_Avoid_: Publisher, Outlet

**Headline**:
The single record for one piece of tracked news content about a Ticker: its title, its direct URL, its raw
content (kept for sentiment analysis), a `category` (`news` or `filing`), when it was published, and —
eventually — a computed `sentiment` (`positive`/`neutral`/`negative`, plus a one-word gloss and a one-sentence
summary).
_Avoid_: Source, Article (an example of the `news` category, not a synonym for the whole concept)
_Category values_: `news`, `filing` — _Avoid (field name)_: kind, type
_Sentiment values_: `positive`, `neutral`, `negative` — _Avoid_: "sentiment category" (collides with `category` above)

**Today** (as used to group Headlines):
The current calendar day in US Eastern time — the stock market's trading day — not UTC and not the viewer's
local timezone. This is a tool about US-market news, so "today" anchors to the market's day regardless of where
it's viewed from. Computed fresh whenever Headlines are grouped, never stored.
_Avoid_: "today" meaning UTC or the browser's local timezone
