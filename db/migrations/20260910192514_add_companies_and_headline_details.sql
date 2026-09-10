-- migrate:up
CREATE TABLE companies (
    ticker TEXT PRIMARY KEY,
    cik TEXT,
    company_name TEXT
);

-- A null cik/company_name is a legitimate state (a real, Finnhub-covered ticker EDGAR's
-- US-filer mapping doesn't recognize) -- not a placeholder to be backfilled. A row only
-- ever exists once some provider has confirmed the ticker is real; see providers.py.

ALTER TABLE headlines ADD COLUMN outlet TEXT;
ALTER TABLE headlines ADD COLUMN summary TEXT;
ALTER TABLE headlines ADD CONSTRAINT headlines_ticker_fkey
    FOREIGN KEY (ticker) REFERENCES companies (ticker);

-- migrate:down
ALTER TABLE headlines DROP CONSTRAINT headlines_ticker_fkey;
ALTER TABLE headlines DROP COLUMN summary;
ALTER TABLE headlines DROP COLUMN outlet;
DROP TABLE companies;
