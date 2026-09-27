-- migrate:up
-- Keyed on Google's own stable `sub` claim, not email -- ADR 0016. email/name/picture_url
-- are overwritten on every sign-in (spec 0006: read-only, always mirrors Google), never
-- edited in-app, so no update trigger is needed here -- the app always writes all three.
CREATE TABLE users (
    sub TEXT PRIMARY KEY,
    email TEXT,
    name TEXT,
    picture_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- migrate:down
DROP TABLE users;
