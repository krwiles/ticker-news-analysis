"""Fetching and normalizing Headline data from external providers.

Deliberately framework-agnostic: no ARQ `ctx`, no FastAPI. `worker.py` wraps
`fetch_and_persist_headlines` as an ARQ job (see ADR 0004); lesson 9's tests
call these functions directly, no worker or server needed.
"""

import asyncio
import functools
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import func, literal_column, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ticker_backend.config import settings
from ticker_backend.db import async_session_factory
from ticker_backend.milvus_client import STORY_PRIMARIES_COLLECTION, ensure_story_primaries_collection, get_milvus_client
from ticker_backend.models import Company, Headline, Story

# Must come after the ticker_backend imports above, not just alphabetized
# with the other third-party imports -- pymilvus's own import unconditionally
# calls load_dotenv() (pymilvus/settings.py), which can inject this repo's
# root .env (meant for docker-compose/dbmate) into os.environ and corrupt
# DATABASE_URL for Settings() if it hasn't been constructed yet. Same
# landmine found and fixed in health.py during spec 0003 -- verified live
# here too: a standalone script importing this module directly broke until
# reordered the same way.
from pymilvus import MilvusException

log = structlog.get_logger()

# Same Eastern-day definition as search.py's own EASTERN (CONTEXT.md's `Today` entry).
EASTERN = ZoneInfo("America/New_York")

# News-worthy filing types only -- excludes routine Form 3/4/5 filings that'd flood results.
# Titles are built from these descriptions since EDGAR's own description just restates the form type.
EDGAR_FORM_DESCRIPTIONS = {
    "10-K": "Annual Report",
    "10-Q": "Quarterly Report",
    "8-K": "Current Report (Material Event)",
    "S-1": "Registration Statement",
    "DEF 14A": "Proxy Statement",
}

# SEC's full ticker-to-CIK mapping -- one file covering every US filer, not a per-ticker endpoint.
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Cheapest OpenAI embedding tier (1536 dimensions) -- see ADR 0007/lesson 18. This dimension count is what
# lesson 19's Milvus collection schema is built against, so changing this model later is a real migration.
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


class ProviderFetchError(Exception):
    """A provider call failed in a way worth a clear, typed signal, not a
    raw KeyError/HTTPError with no context about which provider or ticker."""


# The normalized shape every provider-facing lookup converges on, regardless
# of which provider (or none) actually resolved it.
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
    # Normalize so lookups/cache keys are case-insensitive.
    ticker = ticker.upper()

    # Check the cache first -- if we've already resolved this ticker, return it without calling SEC.
    async with session_factory() as session:
        cached = await session.get(Company, ticker)
        if cached is not None:
            return CompanyInfo(ticker, cached.cik, cached.company_name)

    # Not cached -- fetch SEC's full ticker-to-CIK mapping.
    try:
        response = await client.get(
            SEC_TICKERS_URL, headers={"User-Agent": settings.sec_edgar_user_agent}
        )
        response.raise_for_status()
        all_tickers = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"SEC ticker lookup failed: {exc}") from exc

    # Scan the mapping for a matching ticker, and if found, cache it and return it.
    for entry in all_tickers.values():
        if entry["ticker"].upper() == ticker:
            cik = str(entry["cik_str"])
            company_name = entry["title"]
            async with session_factory() as session:
                await session.merge(Company(ticker=ticker, cik=cik, company_name=company_name))
                await session.commit()
            return CompanyInfo(ticker, cik, company_name)

    # No match in SEC's mapping -- a real, valid outcome, not an error (see docstring).
    return CompanyInfo(ticker, None, None)


async def fetch_edgar_filings(client: httpx.AsyncClient, cik: str | None, ticker: str) -> list[dict]:
    """SEC EDGAR filings for a company, filtered to types that read as news.

    cik=None means SEC's ticker mapping had no match for this ticker --
    not an error, just nothing to fetch.
    """
    # No CIK means SEC doesn't recognize this ticker -- nothing to fetch, not an error.
    if cik is None:
        return []

    # Build this company's submissions-history URL (CIK zero-padded to 10 digits, per EDGAR's own format).
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    # Fetch the company's full filing history.
    try:
        response = await client.get(url, headers={"User-Agent": settings.sec_edgar_user_agent})
        response.raise_for_status()
        recent = response.json()["filings"]["recent"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ProviderFetchError(f"EDGAR filings fetch failed for CIK {cik}: {exc}") from exc

    # EDGAR's "recent" list spans years -- filter to the last week too, same as Finnhub's from/to.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Walk the parallel arrays EDGAR returns (one list per field, same index = same filing) and keep only what matters.
    filings = []
    for i, form in enumerate(recent["form"]):
        # Skip filing types outside this project's news-worthy set (e.g. routine Form 4 ownership filings).
        if form not in EDGAR_FORM_DESCRIPTIONS:
            continue
        published_at = datetime.fromisoformat(recent["acceptanceDateTime"][i])
        # Skip anything older than the 7-day window.
        if published_at < cutoff:
            continue
        # Pull the fields needed to build this filing's real document URL.
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
    # Same trailing 7-day window as EDGAR's.
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=7)
    # Build Finnhub's query params.
    params = {
        "symbol": ticker,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "token": settings.finnhub_api_key,
    }
    # Call Finnhub's company-news endpoint.
    try:
        response = await client.get("https://finnhub.io/api/v1/company-news", params=params)
        response.raise_for_status()
        articles = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"Finnhub news fetch failed for {ticker}: {exc}") from exc

    # Normalize each article into this project's common headline shape.
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


def embedding_input_text(title: str, summary: str | None) -> str:
    """The text actually sent to OpenAI for one headline -- title alone when
    there's no summary, otherwise both joined, per ADR 0007's "title +
    summary, when present" and spec 0002's Story-matching input."""
    if summary is None:
        return title
    return f"{title}\n\n{summary}"


async def get_embeddings(texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
    """Every new headline's embedding in one batched request, not one call
    per headline — see ADR 0007 for why. Each vector is placed by its own
    `index` field, not assumed from array position."""
    # Nothing to embed -- skip the network call entirely rather than send an empty batch.
    if not texts:
        return []

    # One request for the whole batch.
    try:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": OPENAI_EMBEDDING_MODEL, "input": texts},
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"OpenAI embedding fetch failed: {exc}") from exc

    # Place each vector by its own index, not by trusting response order.
    try:
        by_index = {item["index"]: item["embedding"] for item in body["data"]}
        return [by_index[i] for i in range(len(texts))]
    except (KeyError, IndexError) as exc:
        raise ProviderFetchError(f"OpenAI embedding response missing data: {exc}") from exc


async def _run_milvus(func_, *args, **kwargs):
    """Runs one blocking pymilvus call off the event loop -- every Milvus
    call in this module goes through this."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func_, *args, **kwargs))


def _milvus_ticker_day_filter(ticker: str, day: str) -> str:
    """Scopes a Milvus search to one ticker + one calendar day (spec 0002,
    ADR 0006/0011) -- `ticker` comes from the search endpoint's URL, not
    fully validated upstream, so it's escaped before going into the filter
    string; `day` is always built by this module itself, already safe."""
    escaped_ticker = ticker.replace("\\", "\\\\").replace('"', '\\"')
    return f'ticker == "{escaped_ticker}" and day == "{day}"'


async def _match_or_create_story(ticker: str, day: str, vector: list[float], session, milvus) -> uuid.UUID:
    """One headline's matching decision (ADR 0006/0011) -- compares against
    each existing same-day Story's primary, never every member. Never
    touches `headlines` itself; `milvus` is always pre-resolved by the caller."""
    # consistency_level="Strong", not flush() -- see ADR 0011.
    hits = await _run_milvus(
        lambda: milvus.search(
            collection_name=STORY_PRIMARIES_COLLECTION,
            data=[vector],
            filter=_milvus_ticker_day_filter(ticker, day),
            limit=1,
            consistency_level="Strong",
        )
    )
    # A hit above threshold means this headline joins that existing Story.
    if hits and hits[0] and hits[0][0]["distance"] >= settings.story_similarity_threshold:
        return uuid.UUID(hits[0][0]["story_id"])

    # No match -- this headline founds a new Story, and its vector becomes
    # that Story's one representative entry in Milvus, permanently.
    story = Story(ticker=ticker)
    session.add(story)
    await session.flush()
    await _run_milvus(
        lambda: milvus.insert(
            collection_name=STORY_PRIMARIES_COLLECTION,
            data=[{"story_id": str(story.id), "ticker": ticker, "day": day, "embedding": vector}],
        )
    )
    return story.id


async def _assign_stories(
    new_headlines: list[dict], ticker: str, client: httpx.AsyncClient, session_factory, milvus=None
) -> str:
    """Assigns a `story_id` to every genuinely-new headline this run found
    (ADR 0006/0009/0011) -- once set, never touched again. Returns
    "ok"/"skipped"/"error" (ADR 0012); filings always still get grouped
    regardless. `milvus` is injectable for tests, same as `session_factory`."""
    # Filings always get their own Story (CONTEXT.md), committed independently
    # so a later Milvus/OpenAI failure below never undoes this work.
    filing_headlines = [h for h in new_headlines if h["category"] == "filing"]
    if filing_headlines:
        async with session_factory() as session:
            for headline in filing_headlines:
                story = Story(ticker=ticker)
                session.add(story)
                await session.flush()
                await session.execute(
                    update(Headline).where(Headline.id == headline["id"]).values(story_id=story.id)
                )
            await session.commit()

    # News, oldest-published-first: a later headline's candidate Stories
    # include ones a headline earlier in this same loop just created.
    news_headlines = sorted(
        (h for h in new_headlines if h["category"] == "news"), key=lambda h: h["published_at"]
    )
    if not news_headlines:
        return "ok"
    if not settings.openai_api_key:
        return "skipped"

    # Both "not configured" and "configured but failing" degrade gracefully now -- see ADR 0012.
    try:
        # Resolve the real client off the event loop -- a test-injected fake needs no connection at all.
        milvus = milvus if milvus is not None else await _run_milvus(get_milvus_client)
        await _run_milvus(ensure_story_primaries_collection, milvus)
        # Every new news headline's embedding, in one batched request (lesson 18).
        texts = [embedding_input_text(h["title"], h["summary"]) for h in news_headlines]
        embeddings = await get_embeddings(texts, client)

        async with session_factory() as session:
            for headline, vector in zip(news_headlines, embeddings):
                day = headline["published_at"].astimezone(EASTERN).date().isoformat()
                story_id = await _match_or_create_story(ticker, day, vector, session, milvus)
                await session.execute(
                    update(Headline).where(Headline.id == headline["id"]).values(story_id=story_id)
                )
            await session.commit()
    except (ProviderFetchError, MilvusException) as exc:
        # Nothing from this attempt commits -- the session above closes without commit().
        log.warning("providers.grouping_failed", ticker=ticker, error=str(exc))
        return "error"

    return "ok"


async def fetch_and_persist_headlines(ticker: str, session_factory=async_session_factory, milvus=None) -> dict:
    """Fetch EDGAR + Finnhub concurrently, persist the results, report what
    happened. Framework-agnostic (ADR 0004) so tests can call it directly.
    `milvus` threads through to _assign_stories, injectable same as `session_factory`."""
    # Normalize so every downstream lookup/write uses the same casing.
    ticker = ticker.upper()

    # One shared HTTP client for every provider call this run makes.
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Resolve the CIK first (EDGAR needs it) -- a failure here isn't fatal, treat it like a failed provider.
        try:
            company = await get_company(ticker, client, session_factory)
            company_lookup_failed = False
        except ProviderFetchError as exc:
            log.warning("providers.company_lookup_failed", ticker=ticker, error=str(exc))
            company = CompanyInfo(ticker, None, None)
            company_lookup_failed = True

        # Run both provider fetches concurrently -- return_exceptions=True so
        # one provider failing doesn't cancel the other's in-flight request.
        edgar_result, finnhub_result = await asyncio.gather(
            fetch_edgar_filings(client, company.cik, ticker),
            fetch_finnhub_news(client, ticker),
            return_exceptions=True,
        )

    # Accumulators: per-provider ok/error status, and every headline actually fetched.
    providers_status: dict[str, str] = {}
    all_headlines: list[dict] = []

    # Record EDGAR's outcome -- a failed company lookup invalidates its
    # result too (EDGAR needs a real CIK), so both cases are treated as one error.
    if company_lookup_failed or isinstance(edgar_result, Exception):
        if isinstance(edgar_result, Exception):
            log.warning("providers.edgar_failed", ticker=ticker, error=str(edgar_result))
        providers_status["edgar"] = "error"
    else:
        providers_status["edgar"] = "ok"
        all_headlines.extend(edgar_result)

    # Record Finnhub's outcome the same way.
    if isinstance(finnhub_result, Exception):
        log.warning("providers.finnhub_failed", ticker=ticker, error=str(finnhub_result))
        providers_status["finnhub"] = "error"
    else:
        providers_status["finnhub"] = "ok"
        all_headlines.extend(finnhub_result)

    # Persist everything this run actually fetched.
    new_headlines: list[dict] = []
    async with session_factory() as session:
        # Only create the companies row now, and only if real data needs it (see CONTEXT.md's Company entry).
        if company.cik is None and all_headlines:
            await session.merge(Company(ticker=ticker, cik=None, company_name=None))

        # Upsert each headline, deduping by URL -- `xmax = 0` on the returned
        # row distinguishes a genuine INSERT from an ON CONFLICT UPDATE.
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
            ).returning(Headline.id, literal_column("(xmax = 0)").label("was_inserted"))
            row = (await session.execute(stmt)).one()
            if row.was_inserted:
                new_headlines.append({**headline, "id": row.id})

        await session.commit()

    # Group only genuinely-new headlines -- "ok" by default (nothing to group).
    grouping_status = "ok"
    if new_headlines:
        async with httpx.AsyncClient(timeout=10.0) as embed_client:
            grouping_status = await _assign_stories(new_headlines, ticker, embed_client, session_factory, milvus)

    # Map the per-provider outcomes to one overall status the caller can act on.
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
        # Independent of `status` above -- a separate concern (ADR 0012).
        "grouping": grouping_status,
    }
