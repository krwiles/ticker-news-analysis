"""Fetching and normalizing Headline data from external providers.

Deliberately framework-agnostic: no ARQ `ctx`, no FastAPI. `worker.py` wraps
`fetch_and_persist_headlines` as an ARQ job (see ADR 0004); lesson 9's tests
call these functions directly, no worker or server needed.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ticker_backend.config import settings
from ticker_backend.db import async_session_factory
from ticker_backend.models import Company, Headline

log = structlog.get_logger()

# 10-K/10-Q/8-K/S-1/DEF 14A read as news; the raw feed is dominated by routine
# ownership filings (Form 3/4/5) that would otherwise flood the results --
# verified live against AAPL's real filings. Not exhaustive (no 6-K, S-3,
# amendments) -- a reasonable v1 cut, see docs/plans/0007's open items.
# EDGAR's own primaryDocDescription just restates the form type (verified
# live -- "10-Q" for a 10-Q, not a real description), so titles are built
# from this instead.
EDGAR_FORM_DESCRIPTIONS = {
    "10-K": "Annual Report",
    "10-Q": "Quarterly Report",
    "8-K": "Current Report (Material Event)",
    "S-1": "Registration Statement",
    "DEF 14A": "Proxy Statement",
}

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class ProviderFetchError(Exception):
    """A provider call failed in a way worth a clear, typed signal, not a
    raw KeyError/HTTPError with no context about which provider or ticker."""


@dataclass
class CompanyInfo:
    ticker: str
    cik: str | None
    company_name: str | None


async def get_company(
    ticker: str, client: httpx.AsyncClient, session_factory=async_session_factory
) -> CompanyInfo:
    """Resolve a ticker's CIK, caching it in `companies` -- SEC's own ticker
    list is stable reference data, not worth re-fetching on every search.

    If SEC's mapping has no match, returns cik=None *without writing
    anything to `companies` yet* -- whether a row eventually gets created
    depends on what Finnhub returns, decided by the caller.
    """
    ticker = ticker.upper()

    async with session_factory() as session:
        cached = await session.get(Company, ticker)
        if cached is not None:
            return CompanyInfo(ticker, cached.cik, cached.company_name)

    try:
        response = await client.get(
            SEC_TICKERS_URL, headers={"User-Agent": settings.sec_edgar_user_agent}
        )
        response.raise_for_status()
        all_tickers = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"SEC ticker lookup failed: {exc}") from exc

    for entry in all_tickers.values():
        if entry["ticker"].upper() == ticker:
            cik = str(entry["cik_str"])
            company_name = entry["title"]
            async with session_factory() as session:
                await session.merge(Company(ticker=ticker, cik=cik, company_name=company_name))
                await session.commit()
            return CompanyInfo(ticker, cik, company_name)

    return CompanyInfo(ticker, None, None)


async def fetch_edgar_filings(client: httpx.AsyncClient, cik: str | None, ticker: str) -> list[dict]:
    """SEC EDGAR filings for a company, filtered to types that read as news.

    cik=None means SEC's ticker mapping had no match for this ticker --
    not an error, just nothing to fetch.
    """
    if cik is None:
        return []

    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    try:
        response = await client.get(url, headers={"User-Agent": settings.sec_edgar_user_agent})
        response.raise_for_status()
        recent = response.json()["filings"]["recent"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ProviderFetchError(f"EDGAR filings fetch failed for CIK {cik}: {exc}") from exc

    # EDGAR's "recent" list is the company's most recent filings of *any age*
    # (up to ~1000, spanning years) -- filtering by form type alone isn't
    # enough, this pass only wants the last week, same as Finnhub's from/to.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    filings = []
    for i, form in enumerate(recent["form"]):
        if form not in EDGAR_FORM_DESCRIPTIONS:
            continue
        published_at = datetime.fromisoformat(recent["acceptanceDateTime"][i])
        if published_at < cutoff:
            continue
        accession_no_dashes = recent["accessionNumber"][i].replace("-", "")
        primary_doc = recent["primaryDocument"][i]
        filings.append(
            {
                "ticker": ticker,
                "title": f"{form}: {EDGAR_FORM_DESCRIPTIONS[form]}",
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession_no_dashes}/{primary_doc}"
                ),
                "category": "filing",
                "provider": "sec_edgar",
                "outlet": None,
                "summary": None,
                "raw_content": None,
                "published_at": published_at,
            }
        )
    return filings


async def fetch_finnhub_news(client: httpx.AsyncClient, ticker: str) -> list[dict]:
    """Finnhub's real /company-news response, verified live: `source` is the
    original outlet (e.g. "Yahoo"), `summary` is a ready-made blurb. The
    `related` field is NOT used to filter -- verified it isn't a reliable
    "genuinely about this ticker" signal (see spec 0001's Non-goals)."""
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=7)
    params = {
        "symbol": ticker,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "token": settings.finnhub_api_key,
    }
    try:
        response = await client.get("https://finnhub.io/api/v1/company-news", params=params)
        response.raise_for_status()
        articles = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"Finnhub news fetch failed for {ticker}: {exc}") from exc

    return [
        {
            "ticker": ticker,
            "title": article["headline"],
            "url": article["url"],
            "category": "news",
            "provider": "finnhub",
            "outlet": article.get("source"),
            "summary": article.get("summary"),
            "raw_content": None,
            "published_at": datetime.fromtimestamp(article["datetime"], tz=timezone.utc),
        }
        for article in articles
    ]


async def fetch_and_persist_headlines(ticker: str, session_factory=async_session_factory) -> dict:
    """Fetch EDGAR + Finnhub concurrently, persist the results, report what
    happened. Runs as an ARQ job (see worker.py, ADR 0004) -- deliberately
    plain and framework-agnostic so lesson 9 can call it directly."""
    ticker = ticker.upper()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            company = await get_company(ticker, client, session_factory)
            company_lookup_failed = False
        except ProviderFetchError as exc:
            log.warning("providers.company_lookup_failed", ticker=ticker, error=str(exc))
            company = CompanyInfo(ticker, None, None)
            company_lookup_failed = True

        edgar_result, finnhub_result = await asyncio.gather(
            fetch_edgar_filings(client, company.cik, ticker),
            fetch_finnhub_news(client, ticker),
            return_exceptions=True,
        )

    providers_status: dict[str, str] = {}
    all_headlines: list[dict] = []

    if company_lookup_failed or isinstance(edgar_result, Exception):
        if isinstance(edgar_result, Exception):
            log.warning("providers.edgar_failed", ticker=ticker, error=str(edgar_result))
        providers_status["edgar"] = "error"
    else:
        providers_status["edgar"] = "ok"
        all_headlines.extend(edgar_result)

    if isinstance(finnhub_result, Exception):
        log.warning("providers.finnhub_failed", ticker=ticker, error=str(finnhub_result))
        providers_status["finnhub"] = "error"
    else:
        providers_status["finnhub"] = "ok"
        all_headlines.extend(finnhub_result)

    async with session_factory() as session:
        # Finalize the companies row: only now, only if there's real data
        # that needs it -- see CONTEXT.md's Company entry for why this
        # sequencing is what keeps this table free of rows for typos.
        if company.cik is None and all_headlines:
            await session.merge(Company(ticker=ticker, cik=None, company_name=None))

        for headline in all_headlines:
            stmt = pg_insert(Headline).values(**headline)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "title": stmt.excluded.title,
                    "outlet": stmt.excluded.outlet,
                    "summary": stmt.excluded.summary,
                    "fetched_at": func.now(),
                },
            )
            await session.execute(stmt)

        await session.commit()

    ok_count = sum(1 for status in providers_status.values() if status == "ok")
    if ok_count == len(providers_status):
        status = "success"
    elif ok_count == 0:
        status = "complete_failure"
    else:
        status = "partial_failure"

    return {
        "status": status,
        "providers": providers_status,
        "headline_count": len(all_headlines),
    }
