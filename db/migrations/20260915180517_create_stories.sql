-- migrate:up
CREATE TABLE stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL
);

-- Nullable for now -- tightened to NOT NULL once lesson 19's real matching
-- logic exists to populate it on every insert path. Deliberate deviation
-- from ADR 0009's eventual NOT NULL design, same staged-rollout pattern
-- outlet/summary already used (added in a later migration, not day one).
ALTER TABLE headlines ADD COLUMN story_id UUID;
ALTER TABLE headlines ADD CONSTRAINT headlines_story_id_fkey
    FOREIGN KEY (story_id) REFERENCES stories (id);

CREATE INDEX stories_ticker_idx ON stories (ticker);
-- The real query shape: a story's primary headline is always its
-- earliest-published member, derived via `ORDER BY published_at ASC
-- LIMIT 1` -- not stored anywhere, deliberately (see ADR 0009). This
-- composite index also serves plain story_id-only lookups, via B-tree
-- leftmost-prefix matching -- no separate single-column index needed.
CREATE INDEX headlines_story_id_published_at_idx ON headlines (story_id, published_at);

-- migrate:down
ALTER TABLE headlines DROP CONSTRAINT headlines_story_id_fkey;
ALTER TABLE headlines DROP COLUMN story_id;
DROP TABLE stories;
