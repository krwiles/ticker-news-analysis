"""Grouping tests -- OpenAI mocked via respx (same discipline as
test_providers.py), Milvus mocked via a hand-rolled in-memory fake (ADR
0012), not a real connection. See docs/plans/0020-backend-tests-for-grouping.md.

The fake's result shape (`story_id`/`distance`/`entity`) matches exactly
what real Milvus returns, confirmed live in lesson 19 -- every successful-
match test below is itself a regression test for the "id" vs "story_id"
key-naming bug found there, since a wrong key would raise instead of match.

Real limitation, stated once here rather than per-test: an in-memory fake
is always perfectly consistent. It can prove this codebase's own
sequential-loop logic is correct (including the late-match case below), but
it cannot regression-test Milvus's actual `consistency_level="Strong"`
behavior -- that's an infrastructure fact, not application logic, and
already verified live (lesson 19's throwaway scripts, kept around per ADR
0012 rather than promoted into this suite).
"""

import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ticker_backend.config import settings
from ticker_backend.models import Company, Headline, Story
from ticker_backend.providers import ProviderFetchError, _assign_stories, fetch_and_persist_headlines


class _FakeMilvusClient:
    """Stands in for a real MilvusClient -- an in-memory list of rows with a
    real cosine-similarity search(), not canned responses, so tests exercise
    actual matching decisions, not just call counts."""

    def __init__(self):
        self.rows: list[dict] = []

    def has_collection(self, name: str) -> bool:
        # Pretend it already exists -- schema/index creation is Milvus's own
        # concern, already verified live (ADR 0011), not what's under test here.
        return True

    def insert(self, collection_name: str, data: list[dict]) -> None:
        self.rows.extend(data)

    def search(
        self, collection_name: str, data: list[list[float]], filter: str, limit: int, **kwargs
    ) -> list[list[dict]]:
        ticker, day = _parse_ticker_day_filter(filter)
        query = data[0]
        candidates = [row for row in self.rows if row["ticker"] == ticker and row["day"] == day]
        scored = sorted(
            (
                {"story_id": row["story_id"], "distance": _cosine_similarity(query, row["embedding"]), "entity": {}}
                for row in candidates
            ),
            key=lambda hit: hit["distance"],
            reverse=True,
        )
        return [scored[:limit]]


def _parse_ticker_day_filter(filter_expr: str) -> tuple[str, str]:
    match = re.match(r'ticker == "(.*)" and day == "(.*)"', filter_expr)
    assert match, f"unexpected filter expression: {filter_expr!r}"
    return match.group(1), match.group(2)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


def _openai_response(vectors: list[list[float]]) -> dict:
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": v, "index": i} for i, v in enumerate(vectors)],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def _headline(ticker: str, url: str, title: str, published_at: datetime, category="news", summary=None):
    return {
        "ticker": ticker,
        "title": title,
        "url": url,
        "category": category,
        "provider": "finnhub",
        "outlet": "Yahoo",
        "summary": summary,
        "raw_content": None,
        "published_at": published_at,
    }


async def _insert_new(session_factory, headline_dict: dict) -> dict:
    """Mirrors fetch_and_persist_headlines' own xmax=0 upsert -- returns the
    dict with a real `id`, the exact shape _assign_stories expects."""
    async with session_factory() as session:
        await session.merge(Company(ticker=headline_dict["ticker"]))
        stmt = pg_insert(Headline).values(**headline_dict)
        stmt = stmt.on_conflict_do_update(
            index_elements=["url"], set_={"title": stmt.excluded.title}
        ).returning(Headline.id, literal_column("(xmax = 0)").label("was_inserted"))
        row = (await session.execute(stmt)).one()
        await session.commit()
        assert row.was_inserted, "test setup expected a genuinely new row"
        return {**headline_dict, "id": row.id}


@pytest.fixture
def openai_configured(monkeypatch):
    """These tests need settings.openai_api_key truthy to reach the
    news-matching path at all -- real test/CI environments never have one
    configured (see test_grouping_skipped_when_openai_not_configured, which
    deliberately does NOT use this fixture)."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")


NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)


@respx.mock
async def test_matching_groups_same_event_different_wording(test_session_factory, openai_configured):
    original = await _insert_new(
        test_session_factory, _headline("AAPL", "https://example.com/g1", "Original headline", NOW)
    )
    duplicate = await _insert_new(
        test_session_factory, _headline("AAPL", "https://example.com/g2", "Duplicate headline", NOW + timedelta(minutes=1))
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0], [0.8, 0.6]]))  # cosine 0.8 -- above 0.75
    )

    fake = _FakeMilvusClient()
    async with httpx.AsyncClient() as client:
        status = await _assign_stories([original, duplicate], "AAPL", client, test_session_factory, milvus=fake)

    assert status == "ok"
    async with test_session_factory() as session:
        rows = (await session.execute(select(Headline).where(Headline.ticker == "AAPL"))).scalars().all()
    story_ids = {r.story_id for r in rows}
    assert len(story_ids) == 1, "genuinely similar headlines should share one Story"


@respx.mock
async def test_matching_keeps_genuinely_different_headlines_separate(test_session_factory, openai_configured):
    first = await _insert_new(test_session_factory, _headline("MSFT", "https://example.com/g3", "First headline", NOW))
    second = await _insert_new(
        test_session_factory, _headline("MSFT", "https://example.com/g4", "Second headline", NOW + timedelta(minutes=1))
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0], [0.0, 1.0]]))  # cosine 0 -- below 0.75
    )

    fake = _FakeMilvusClient()
    async with httpx.AsyncClient() as client:
        await _assign_stories([first, second], "MSFT", client, test_session_factory, milvus=fake)

    async with test_session_factory() as session:
        rows = (await session.execute(select(Headline).where(Headline.ticker == "MSFT"))).scalars().all()
    story_ids = {r.story_id for r in rows}
    assert len(story_ids) == 2, "genuinely different headlines must never incorrectly group"


@respx.mock
async def test_matching_never_spans_two_tickers(test_session_factory, openai_configured):
    """Identical vectors, different tickers -- grouping is scoped per-ticker
    (ADR 0006), same as search itself already is."""
    aapl = await _insert_new(test_session_factory, _headline("AAPL", "https://example.com/g5", "Headline", NOW))
    msft = await _insert_new(test_session_factory, _headline("MSFT", "https://example.com/g6", "Headline", NOW))

    fake = _FakeMilvusClient()
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
    )
    async with httpx.AsyncClient() as client:
        await _assign_stories([aapl], "AAPL", client, test_session_factory, milvus=fake)
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
    )
    async with httpx.AsyncClient() as client:
        await _assign_stories([msft], "MSFT", client, test_session_factory, milvus=fake)

    async with test_session_factory() as session:
        aapl_row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/g5"))).scalar_one()
        msft_row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/g6"))).scalar_one()
    assert aapl_row.story_id != msft_row.story_id


@respx.mock
async def test_matching_never_spans_two_days(test_session_factory, openai_configured):
    """Identical vectors, same ticker, different calendar day -- day-scoping
    (ADR 0006) is what prevents recurring-report language from incorrectly
    merging across reporting periods (empirically confirmed in ADR 0011:
    the highest-scoring real pair measured was exactly this shape)."""
    today = await _insert_new(test_session_factory, _headline("TSLA", "https://example.com/g7", "Headline", NOW))
    tomorrow = await _insert_new(
        test_session_factory, _headline("TSLA", "https://example.com/g8", "Headline", NOW + timedelta(days=1))
    )

    fake = _FakeMilvusClient()
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
    )
    async with httpx.AsyncClient() as client:
        await _assign_stories([today], "TSLA", client, test_session_factory, milvus=fake)
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
    )
    async with httpx.AsyncClient() as client:
        await _assign_stories([tomorrow], "TSLA", client, test_session_factory, milvus=fake)

    async with test_session_factory() as session:
        row1 = (await session.execute(select(Headline).where(Headline.url == "https://example.com/g7"))).scalar_one()
        row2 = (await session.execute(select(Headline).where(Headline.url == "https://example.com/g8"))).scalar_one()
    assert row1.story_id != row2.story_id


async def test_filings_always_get_their_own_story(test_session_factory):
    """Filings never participate in grouping, even with each other, by
    construction (CONTEXT.md's Story entry) -- no OpenAI/Milvus call
    involved at all, so this needs no respx mock and no fake client."""
    filing_a = await _insert_new(
        test_session_factory, _headline("AAPL", "https://example.com/f1", "8-K: filing A", NOW, category="filing")
    )
    filing_b = await _insert_new(
        test_session_factory, _headline("AAPL", "https://example.com/f2", "8-K: filing B", NOW, category="filing")
    )

    async with httpx.AsyncClient() as client:
        status = await _assign_stories([filing_a, filing_b], "AAPL", client, test_session_factory)

    assert status == "ok"
    async with test_session_factory() as session:
        rows = (
            await session.execute(select(Headline).where(Headline.url.in_(["https://example.com/f1", "https://example.com/f2"])))
        ).scalars().all()
    story_ids = {r.story_id for r in rows}
    assert len(story_ids) == 2
    assert None not in story_ids


@respx.mock
async def test_late_match_finds_story_many_iterations_later(test_session_factory, openai_configured):
    """A headline should still correctly match an existing Story many
    iterations after that Story was created, not just on the very next
    search -- confirmed live against real Milvus in lesson 19's follow-up
    (NOTES.md). This proves this codebase's sequential-loop logic handles
    that correctly; see the module docstring for what it does NOT prove."""
    original = await _insert_new(test_session_factory, _headline("NFLX", "https://example.com/late-0", "Original", NOW))
    fillers = [
        await _insert_new(
            test_session_factory,
            _headline("NFLX", f"https://example.com/late-{i}", f"Unrelated filler {i}", NOW + timedelta(minutes=i)),
        )
        for i in range(1, 11)
    ]
    late_duplicate = await _insert_new(
        test_session_factory, _headline("NFLX", "https://example.com/late-11", "Duplicate of original", NOW + timedelta(minutes=11))
    )

    # 11-dimensional one-hot vectors: original lives on axis 0, each filler
    # gets its own distinct axis (1-10) -- perfectly orthogonal to every
    # other filler and to the original (cosine 0), so none of them can
    # accidentally match anything. The late duplicate is a near-duplicate
    # of the original (mostly axis 0, a small nudge into axis 1) -- still
    # far below threshold against filler 1's own pure axis-1 vector.
    def _one_hot(i: int) -> list[float]:
        v = [0.0] * 11
        v[i] = 1.0
        return v

    filler_vectors = [_one_hot(i) for i in range(1, 11)]
    duplicate_vector = _one_hot(0)
    duplicate_vector[1] = 0.1
    vectors = [_one_hot(0)] + filler_vectors + [duplicate_vector]
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=httpx.Response(200, json=_openai_response(vectors)))

    fake = _FakeMilvusClient()
    async with httpx.AsyncClient() as client:
        await _assign_stories([original, *fillers, late_duplicate], "NFLX", client, test_session_factory, milvus=fake)

    async with test_session_factory() as session:
        original_row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/late-0"))).scalar_one()
        late_row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/late-11"))).scalar_one()
        filler_rows = (
            await session.execute(select(Headline).where(Headline.url.like("https://example.com/late-%")))
        ).scalars().all()

    distinct_stories = {r.story_id for r in filler_rows}
    assert len(distinct_stories) >= 10, "fillers should mostly stay distinct from each other and the original"
    assert original_row.story_id == late_row.story_id


async def test_permanence_second_run_never_reconsiders_known_headlines(test_session_factory):
    """Re-searching/refreshing doesn't reshuffle or duplicate existing
    Stories (spec 0002) -- proven at the fetch_and_persist_headlines level,
    since that's where the xmax=0 new-vs-known decision actually lives, not
    inside _assign_stories itself. Second call must not touch OpenAI at
    all: the headline is no longer "new", so it's never handed to grouping
    a second time -- checked via respx's own call count, not just the
    outcome staying the same."""
    with respx.mock:
        respx.get("https://www.sec.gov/files/company_tickers.json").mock(return_value=httpx.Response(200, json={}))
        respx.get(url__regex=r"https://data\.sec\.gov/.*").mock(return_value=httpx.Response(200, json={"filings": {"recent": {k: [] for k in ["form", "filingDate", "acceptanceDateTime", "accessionNumber", "primaryDocument", "primaryDocDescription"]}}}))
        respx.get("https://finnhub.io/api/v1/company-news").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "category": "company",
                        "datetime": int(NOW.timestamp()),
                        "headline": "A real headline",
                        "id": 1,
                        "related": "GOOG",
                        "source": "Yahoo",
                        "summary": "A summary.",
                        "url": "https://example.com/perm-1",
                    }
                ],
            )
        )
        embeddings_route = respx.post("https://api.openai.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
        )
        fake = _FakeMilvusClient()

        async def run():
            return await fetch_and_persist_headlines("GOOG", session_factory=test_session_factory, milvus=fake)

        settings.openai_api_key = "test-key-not-real"
        try:
            first = await run()
            second = await run()
        finally:
            settings.openai_api_key = ""

    assert first["headline_count"] == second["headline_count"] == 1
    assert embeddings_route.call_count == 1, "the second run must never re-embed an already-known headline"

    async with test_session_factory() as session:
        row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/perm-1"))).scalar_one()
    assert row.story_id is not None


async def test_grouping_skipped_when_openai_not_configured(test_session_factory):
    headline = await _insert_new(test_session_factory, _headline("AAPL", "https://example.com/skip-1", "Headline", NOW))
    assert settings.openai_api_key == ""  # the real default in this test environment

    async with httpx.AsyncClient() as client:
        status = await _assign_stories([headline], "AAPL", client, test_session_factory)

    assert status == "skipped"
    async with test_session_factory() as session:
        row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/skip-1"))).scalar_one()
    assert row.story_id is None


@respx.mock
async def test_grouping_error_when_openai_fails(test_session_factory, openai_configured):
    """Configured but unreachable/failing -- degrades gracefully (ADR 0012),
    distinct from "skipped": the headline still persists, grouping is
    flagged as "error" rather than silently indistinguishable from "not
    configured", and the whole job does not crash."""
    headline = await _insert_new(test_session_factory, _headline("AAPL", "https://example.com/err-1", "Headline", NOW))
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=httpx.Response(401, json={"error": "bad key"}))

    async with httpx.AsyncClient() as client:
        status = await _assign_stories([headline], "AAPL", client, test_session_factory)

    assert status == "error"
    async with test_session_factory() as session:
        row = (await session.execute(select(Headline).where(Headline.url == "https://example.com/err-1"))).scalar_one()
    assert row.story_id is None  # nothing partial committed -- see _assign_stories' own rollback reasoning


@respx.mock
async def test_grouping_error_when_milvus_fails(test_session_factory, openai_configured):
    from pymilvus import MilvusException

    class _BrokenMilvusClient(_FakeMilvusClient):
        def search(self, *args, **kwargs):
            raise MilvusException("simulated Milvus outage")

    headline = await _insert_new(test_session_factory, _headline("AAPL", "https://example.com/err-2", "Headline", NOW))
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_openai_response([[1.0, 0.0]]))
    )

    async with httpx.AsyncClient() as client:
        status = await _assign_stories([headline], "AAPL", client, test_session_factory, milvus=_BrokenMilvusClient())

    assert status == "error"
