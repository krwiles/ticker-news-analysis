-- migrate:up
CREATE TABLE headlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('news', 'filing')),
    provider TEXT NOT NULL,
    raw_content TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per distinct source URL — this is the dedup mechanism spec 0001 and ADR 0003 describe: a live fetch
-- upserts ON CONFLICT (url), so re-fetching something already seen updates it instead of duplicating it.
CREATE UNIQUE INDEX headlines_url_idx ON headlines (url);

-- Every real query this feature makes is "recent headlines for this ticker" — this is the index that matters.
CREATE INDEX headlines_ticker_published_at_idx ON headlines (ticker, published_at DESC);

-- migrate:down
DROP TABLE headlines;
