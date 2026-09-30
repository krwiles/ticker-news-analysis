-- migrate:up
-- One row per (user, ticker) a User is tracking -- spec 0008, ADR 0019. Real FKs, matching
-- the precedent headlines.ticker -> companies.ticker already sets: the ticker FK is what
-- enforces "add requires an already-known ticker" at the database, not a separate pre-check.
CREATE TABLE watchlist_entries (
    user_sub TEXT NOT NULL REFERENCES users (sub),
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_sub, ticker)
);

-- migrate:down
DROP TABLE watchlist_entries;
