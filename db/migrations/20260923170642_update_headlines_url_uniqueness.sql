-- migrate:up

-- A shared article (the same URL genuinely returned by Finnhub for two different tickers' feeds,
-- confirmed live -- lesson 34) used to be silently hidden from every ticker but the first one to
-- fetch it. Uniqueness moves to (ticker, url): a shared article now gets one row per ticker,
-- accepting some duplication in exchange for never hiding real news (plan 0035).
DROP INDEX headlines_url_idx;
CREATE UNIQUE INDEX headlines_ticker_url_idx ON headlines (ticker, url);

-- migrate:down
DROP INDEX headlines_ticker_url_idx;
CREATE UNIQUE INDEX headlines_url_idx ON headlines (url);
