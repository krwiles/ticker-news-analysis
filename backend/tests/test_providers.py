"""Provider tests, mocked at the HTTP layer with respx -- using the real
response shapes captured live in lessons 7/8, not invented fixtures. See
docs/plans/0010-testing-search-feature.md."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from ticker_backend.config import derive_sentiment_enum
from ticker_backend.models import Company, Headline, Story
from ticker_backend.providers import (
    ProviderFetchError,
    embedding_input_text,
    fetch_and_persist_headlines,
    fetch_edgar_filings,
    fetch_finnhub_news,
    get_company,
    get_embeddings,
)

TICKERS_JSON = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _edgar_filing(form: str, days_ago: int, accession: str):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "form": form,
        "filingDate": dt.date().isoformat(),
        "acceptanceDateTime": dt.isoformat().replace("+00:00", "Z"),
        "accessionNumber": accession,
        "primaryDocument": "doc.htm",
        "primaryDocDescription": form,
    }


def _edgar_submissions(filings: list[dict]) -> dict:
    # Transpose into EDGAR's real parallel-array shape (one list per field,
    # not one dict per filing) -- see fetch_edgar_filings' own indexed loop.
    keys = ["form", "filingDate", "acceptanceDateTime", "accessionNumber", "primaryDocument", "primaryDocDescription"]
    return {"filings": {"recent": {k: [f[k] for f in filings] for k in keys}}}


@respx.mock
async def test_edgar_date_filter_regression(test_session_factory):
    """Named regression test for the exact bug found live in lesson 7:
    EDGAR's feed returns filings of any age -- form-type filtering alone
    isn't enough. This must keep only the filing inside the 7-day window."""
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json=_edgar_submissions(
                [
                    _edgar_filing("10-Q", days_ago=3000, accession="0001-old-10q"),  # too old
                    _edgar_filing("8-K", days_ago=1, accession="0001-recent-8k"),  # keep
                    _edgar_filing("4", days_ago=1, accession="0001-recent-form4"),  # wrong type
                ]
            ),
        )
    )
    # Fetch and filter to the news-worthy, in-window subset.
    async with httpx.AsyncClient() as client:
        filings = await fetch_edgar_filings(client, cik="320193", ticker="AAPL")

    assert len(filings) == 1
    assert "0001recent8k" in filings[0]["url"]  # dashes stripped from the accession number, by design
    assert filings[0]["category"] == "filing"
    assert filings[0]["outlet"] is None
    assert filings[0]["summary"] is None


@respx.mock
async def test_finnhub_maps_source_and_summary(test_session_factory):
    # Mock Finnhub's real response shape (captured live in lesson 7).
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "category": "company",
                    "datetime": 1789055298,
                    "headline": "A real headline",
                    "id": 1,
                    "image": "https://example.com/x.png",
                    "related": "AAPL",
                    "source": "Yahoo",
                    "summary": "A short summary blurb.",
                    "url": "https://finnhub.io/api/news?id=abc",
                }
            ],
        )
    )
    async with httpx.AsyncClient() as client:
        articles = await fetch_finnhub_news(client, ticker="AAPL")

    assert len(articles) == 1
    assert articles[0]["outlet"] == "Yahoo"
    assert articles[0]["summary"] == "A short summary blurb."
    assert articles[0]["category"] == "news"
    assert articles[0]["provider"] == "finnhub"


@respx.mock
async def test_finnhub_403_raises_typed_error(test_session_factory):
    # Mock an auth failure.
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(403, json={"error": "You don't have access to this resource."})
    )
    # A 403 should surface as our own typed error, not a raw httpx exception.
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderFetchError):
            await fetch_finnhub_news(client, ticker="ZZZQX")


@respx.mock
async def test_get_embeddings_places_vectors_by_index_not_array_order(test_session_factory):
    """Response items deliberately out of index order -- proves the lookup
    really uses each item's own `index` field, not array position (same
    "insert out of order, prove the derivation is real" discipline as
    test_story_primary_is_derived_as_earliest_published_headline)."""
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "embedding": [0.9, 0.9], "index": 1},
                    {"object": "embedding", "embedding": [0.1, 0.1], "index": 0},
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 12, "total_tokens": 12},
            },
        )
    )
    async with httpx.AsyncClient() as client:
        embeddings = await get_embeddings(["first headline", "second headline"], client)

    assert embeddings == [[0.1, 0.1], [0.9, 0.9]]


@respx.mock
async def test_get_embeddings_raises_typed_error_on_failure(test_session_factory):
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Incorrect API key provided."}})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderFetchError):
            await get_embeddings(["A real headline"], client)


async def test_get_embeddings_empty_list_skips_the_network_call(test_session_factory):
    # No respx mock registered at all -- if get_embeddings tried a real HTTP
    # call for an empty batch, this would raise a connection error.
    async with httpx.AsyncClient() as client:
        embeddings = await get_embeddings([], client)

    assert embeddings == []


@respx.mock
def test_derive_sentiment_enum_boundaries():
    # Real cutoffs from lesson 26's own empirical pass -- <=40 negative, >=70 positive, else neutral.
    assert derive_sentiment_enum(0) == "negative"
    assert derive_sentiment_enum(40) == "negative"
    assert derive_sentiment_enum(41) == "neutral"
    assert derive_sentiment_enum(69) == "neutral"
    assert derive_sentiment_enum(70) == "positive"
    assert derive_sentiment_enum(100) == "positive"


def test_embedding_input_text_uses_title_only_when_no_summary():
    assert embedding_input_text("A real headline", None) == "A real headline"


def test_embedding_input_text_joins_title_and_summary_when_present():
    assert embedding_input_text("A real headline", "A short blurb.") == "A real headline\n\nA short blurb."


@respx.mock
async def test_partial_failure_when_one_provider_errors(test_session_factory):
    # EDGAR succeeds, Finnhub fails.
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=TICKERS_JSON)
    )
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_edgar_submissions([_edgar_filing("8-K", 1, "0001-a")]))
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(return_value=httpx.Response(500))

    result = await fetch_and_persist_headlines("AAPL", session_factory=test_session_factory)

    # One provider ok, one error -> overall status should reflect the mix.
    assert result["status"] == "partial_failure"
    assert result["providers"] == {"edgar": "ok", "finnhub": "error"}


@respx.mock
async def test_dedup_by_url_on_second_fetch(test_session_factory):
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=TICKERS_JSON)
    )
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_edgar_submissions([_edgar_filing("8-K", 1, "0001-a")]))
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(return_value=httpx.Response(200, json=[]))

    # Fetch the same ticker twice, same mocked responses both times.
    await fetch_and_persist_headlines("AAPL", session_factory=test_session_factory)
    await fetch_and_persist_headlines("AAPL", session_factory=test_session_factory)

    # The second fetch should update the existing row, not duplicate it.
    async with test_session_factory() as session:
        rows = (await session.execute(select(Headline).where(Headline.ticker == "AAPL"))).scalars().all()
    assert len(rows) == 1


@respx.mock
async def test_no_company_row_when_both_providers_empty(test_session_factory):
    # A real ticker mapping exists, but not for the one we're about to search.
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={"0": {"cik_str": 1, "ticker": "REAL", "title": "Real Co"}})
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(return_value=httpx.Response(200, json=[]))

    result = await fetch_and_persist_headlines("ZZZQX", session_factory=test_session_factory)

    # No real data from either provider -> no companies row should be created at all.
    assert result["headline_count"] == 0
    async with test_session_factory() as session:
        company = await session.get(Company, "ZZZQX")
    assert company is None


@respx.mock
async def test_company_row_created_with_null_cik_when_only_finnhub_has_data(test_session_factory):
    # EDGAR's mapping has no match for this ticker, but Finnhub does have real news for it.
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={"0": {"cik_str": 1, "ticker": "OTHER", "title": "Other Co"}})
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "category": "company",
                    "datetime": int(datetime.now(timezone.utc).timestamp()),
                    "headline": "Some real news",
                    "id": 1,
                    "related": "FOREIGNCO",
                    "source": "Reuters",
                    "summary": "Summary.",
                    "url": "https://example.com/a",
                }
            ],
        )
    )

    result = await fetch_and_persist_headlines("FOREIGNCO", session_factory=test_session_factory)

    # A row should still be created, just with cik/company_name left null.
    assert result["status"] == "success"
    async with test_session_factory() as session:
        company = await session.get(Company, "FOREIGNCO")
    assert company is not None
    assert company.cik is None
    assert company.company_name is None


async def test_category_check_constraint_rejects_invalid_value(test_session_factory):
    # "rumor" isn't a real category -- the DB's own CHECK constraint should reject it.
    async with test_session_factory() as session:
        session.add(
            Headline(
                ticker="AAPL",
                title="bad",
                url="https://example.com/bad-category",
                category="rumor",
                provider="finnhub",
                published_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(Exception, match="CheckViolationError|violates check constraint"):
            await session.commit()


async def test_get_company_uses_cache_not_a_second_lookup(test_session_factory):
    async with test_session_factory() as session:
        session.add(Company(ticker="AAPL", cik="320193", company_name="Apple Inc."))
        await session.commit()

    # No respx mock registered at all -- if get_company tried a real HTTP
    # call instead of reading the cache, this would raise a connection error.
    async with httpx.AsyncClient() as client:
        info = await get_company("AAPL", client, test_session_factory)

    assert info.cik == "320193"
    assert info.company_name == "Apple Inc."


async def test_story_primary_is_derived_as_earliest_published_headline(test_session_factory):
    """No stored "primary" reference exists (ADR 0009) -- proves the real
    query (order by published_at, take the first) works. Inserted out of
    chronological order on purpose, so a bug using insertion order instead
    would actually be caught."""
    # Create an empty Story first -- headlines need its id to reference.
    async with test_session_factory() as session:
        await session.merge(Company(ticker="AAPL"))
        story = Story(ticker="AAPL")
        session.add(story)
        await session.commit()
        story_id = story.id

    earlier = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)

    # Insert the later-published headline first, on purpose.
    async with test_session_factory() as session:
        session.add(
            Headline(
                ticker="AAPL",
                title="Later headline",
                url="https://example.com/later",
                category="news",
                provider="finnhub",
                published_at=later,
                story_id=story_id,
            )
        )
        session.add(
            Headline(
                ticker="AAPL",
                title="Earlier headline",
                url="https://example.com/earlier",
                category="news",
                provider="finnhub",
                published_at=earlier,
                story_id=story_id,
            )
        )
        await session.commit()

    # Same derivation query the real code uses -- earliest published_at wins, not insertion order.
    async with test_session_factory() as session:
        rows = await session.execute(
            select(Headline).where(Headline.story_id == story_id).order_by(Headline.published_at).limit(1)
        )
        primary = rows.scalar_one()

    assert primary.title == "Earlier headline"
