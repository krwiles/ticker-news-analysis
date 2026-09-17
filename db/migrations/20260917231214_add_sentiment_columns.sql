-- migrate:up

-- All nullable, no backfill -- NULL means "not yet attempted", the same
-- staged-rollout pattern outlet/summary/story_id already used. Plain TEXT,
-- no CHECK constraints -- matches the existing category column's own
-- precedent (Python-side Literal typing only). No stored enum column:
-- positive/neutral/negative is derived from sentiment_score at read time,
-- not stored (see spec 0005 / ADR 0014 / ADR 0009's own derive-don't-store
-- precedent).
ALTER TABLE headlines ADD COLUMN sentiment_score INTEGER;
ALTER TABLE headlines ADD COLUMN sentiment_gloss TEXT;
ALTER TABLE headlines ADD COLUMN sentiment_rationale TEXT;
ALTER TABLE headlines ADD COLUMN sentiment_status TEXT;

-- sentiment_average stays nullable -- there's no average until the first
-- member actually reaches a real score; 0 would be a real, wrong value.
-- sentiment_score_count is a real count, starts at zero, not unknown --
-- only counts members that reached sentiment_status = 'ok' (ADR 0014):
-- skipped/error members never contribute.
ALTER TABLE stories ADD COLUMN sentiment_average DOUBLE PRECISION;
ALTER TABLE stories ADD COLUMN sentiment_score_count INTEGER NOT NULL DEFAULT 0;

-- migrate:down

ALTER TABLE stories DROP COLUMN sentiment_score_count;
ALTER TABLE stories DROP COLUMN sentiment_average;

ALTER TABLE headlines DROP COLUMN sentiment_status;
ALTER TABLE headlines DROP COLUMN sentiment_rationale;
ALTER TABLE headlines DROP COLUMN sentiment_gloss;
ALTER TABLE headlines DROP COLUMN sentiment_score;
