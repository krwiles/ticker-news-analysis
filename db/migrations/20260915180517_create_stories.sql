-- migrate:up
CREATE TABLE stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    -- Nullable permanently, not just at rollout: a stories row is written
    -- before the headline it will call primary exists yet (that headline
    -- needs a valid stories.id to reference first) -- see ADR 0009.
    primary_headline_id UUID
);

-- Nullable for now -- tightened to NOT NULL once lesson 19's real matching
-- logic exists to populate it on every insert path. Deliberate deviation
-- from ADR 0009's eventual NOT NULL design, same staged-rollout pattern
-- outlet/summary already used (added in a later migration, not day one).
ALTER TABLE headlines ADD COLUMN story_id UUID;

-- Circular FK: stories.primary_headline_id -> headlines.id and
-- headlines.story_id -> stories.id. Both tables/columns have to exist
-- before either constraint can be added.
ALTER TABLE headlines ADD CONSTRAINT headlines_story_id_fkey
    FOREIGN KEY (story_id) REFERENCES stories (id);
ALTER TABLE stories ADD CONSTRAINT stories_primary_headline_id_fkey
    FOREIGN KEY (primary_headline_id) REFERENCES headlines (id);
-- A headline can be at most one story's primary.
ALTER TABLE stories ADD CONSTRAINT stories_primary_headline_id_key UNIQUE (primary_headline_id);

CREATE INDEX stories_ticker_idx ON stories (ticker);
CREATE INDEX headlines_story_id_idx ON headlines (story_id);

-- migrate:down
ALTER TABLE stories DROP CONSTRAINT stories_primary_headline_id_key;
ALTER TABLE stories DROP CONSTRAINT stories_primary_headline_id_fkey;
ALTER TABLE headlines DROP CONSTRAINT headlines_story_id_fkey;
ALTER TABLE headlines DROP COLUMN story_id;
DROP TABLE stories;
