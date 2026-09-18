"""Sentiment tests, mocked at the HTTP layer with respx -- same discipline as
test_providers.py. See docs/plans/0023-*.md through 0026-*.md and ADR 0014."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

import ticker_backend.sentiment as sentiment_module
from ticker_backend.config import settings
from ticker_backend.models import Company, Headline, Story
from ticker_backend.providers import ProviderFetchError
from ticker_backend.sentiment import (
    FILING_CONTENT_CAP_CHARS,
    _extract_relevant_filing_section,
    _strip_html_to_text,
    compute_and_persist_sentiment,
    get_filing_content,
    get_sentiment,
)


async def _seed_headline_for_sentiment(
    session_factory,
    ticker: str,
    url: str,
    story_id=None,
    sentiment_status=None,
    category="news",
    title="A real headline",
    published_at=None,
):
    """A news Headline ready for compute_and_persist_sentiment -- real
    Company row first (headlines.ticker's own FK, same as providers.py's
    real insert path), published just now (unless overridden) so it falls
    inside the recent window every test implicitly relies on."""
    async with session_factory() as session:
        await session.merge(Company(ticker=ticker))
        session.add(
            Headline(
                ticker=ticker,
                title=title,
                url=url,
                category=category,
                provider="finnhub",
                summary="A short blurb.",
                published_at=published_at or datetime.now(timezone.utc),
                story_id=story_id,
                sentiment_status=sentiment_status,
            )
        )
        await session.commit()


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    # Real value (SENTIMENT_RETRY_DELAY_SECONDS) is a deliberate pause between attempts -- fine in
    # production, but would make every retry test slow for no real signal. Autouse: no sentiment
    # test benefits from waiting for real, and non-sentiment tests never read this constant at all.
    monkeypatch.setattr(sentiment_module, "SENTIMENT_RETRY_DELAY_SECONDS", 0)


@respx.mock
async def test_get_sentiment_returns_structured_score_gloss_rationale(test_session_factory):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"score": 90, "gloss": "bullish", "rationale": "Strong earnings beat."}'
                        }
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        sentiment = await get_sentiment("Apple beats earnings expectations.", client)

    assert sentiment == {"score": 90, "gloss": "bullish", "rationale": "Strong earnings beat."}


@respx.mock
async def test_get_sentiment_raises_typed_error_on_failure(test_session_factory):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Incorrect API key provided."}})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderFetchError):
            await get_sentiment("A real headline", client)


def test_strip_html_to_text_removes_tags():
    assert _strip_html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_to_text_decodes_numeric_entities():
    assert _strip_html_to_text("Item&#160;7.") == "Item 7."


def test_extract_relevant_filing_section_finds_real_content_and_stops_at_next_heading():
    # A TOC-style early mention (bare "Item 7.", no real title after it) must not match --
    # only the real heading, verified live to need "Management"/"MANAGEMENT" immediately after.
    text = (
        "TABLE OF CONTENTS Item 7. Page 24 "
        "Item 7. Management's Discussion and Analysis of Financial Condition. "
        "Real MD&A narrative content about the business goes here. "
        "Item 7A. Quantitative and Qualitative Disclosures. Market risk content."
    )
    section = _extract_relevant_filing_section(text)
    assert "Real MD&A narrative content" in section
    assert "Market risk content" not in section


def test_extract_relevant_filing_section_falls_back_to_document_start_when_incorporated_by_reference():
    # Mirrors the one real filer found live (Friedman Industries) whose actual MD&A isn't in
    # this document at all -- the real content living at the document's own start must be
    # used instead of the reference-only Item 7 section.
    text = (
        "FORM 10-K ANNUAL REPORT. REAL BUSINESS CONTENT describing the company at the very start. "
        "Item 1. Business. More business description. "
        "Item 7. Management's Discussion and Analysis. "
        "Information with respect to Item 7 is hereby incorporated herein by reference "
        "from the Company's Annual Report to Shareholders."
    )
    section = _extract_relevant_filing_section(text)
    assert "REAL BUSINESS CONTENT" in section
    assert section.startswith("FORM 10-K")


def test_extract_relevant_filing_section_uses_document_start_when_no_item_7_heading():
    # Mirrors an 8-K/S-1/DEF 14A -- none of these use "Item 7" MD&A numbering at all.
    text = "FORM 8-K CURRENT REPORT. A material event occurred. No Item 7 exists in an 8-K."
    assert _extract_relevant_filing_section(text) == text


def test_extract_relevant_filing_section_caps_length():
    text = "Item 7. Management's Discussion and Analysis. " + ("word " * 50_000)
    section = _extract_relevant_filing_section(text)
    assert len(section) == FILING_CONTENT_CAP_CHARS


@respx.mock
async def test_get_filing_content_extracts_and_returns_section(test_session_factory):
    respx.get("https://example.com/filing.htm").mock(
        return_value=httpx.Response(
            200, text="<html><body><p>Item 7. Management's Discussion. Real content.</p></body></html>"
        )
    )
    async with httpx.AsyncClient() as client:
        content = await get_filing_content("https://example.com/filing.htm", client)

    assert "Real content" in content


@respx.mock
async def test_get_filing_content_raises_typed_error_on_failure(test_session_factory):
    respx.get("https://example.com/filing.htm").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderFetchError):
            await get_filing_content("https://example.com/filing.htm", client)


@pytest.fixture
def openai_configured(monkeypatch):
    # Real test/CI environments never have a real key configured -- see
    # test_compute_and_persist_sentiment_skipped_when_not_configured, which
    # deliberately does NOT use this fixture.
    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")


def _sentiment_response(score: int, gloss: str, rationale: str) -> httpx.Response:
    import json as _json

    return httpx.Response(
        200, json={"choices": [{"message": {"content": _json.dumps({"score": score, "gloss": gloss, "rationale": rationale})}}]}
    )


@respx.mock
async def test_compute_and_persist_sentiment_persists_real_score(test_session_factory, openai_configured):
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-1")
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_sentiment_response(90, "bullish", "Strong results.")
    )

    result = await compute_and_persist_sentiment("AAPL", test_session_factory)

    assert result == {"status": "ok"}
    async with test_session_factory() as session:
        headline = (await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-1"))).scalar_one()
    assert headline.sentiment_score == 90
    assert headline.sentiment_gloss == "bullish"
    assert headline.sentiment_rationale == "Strong results."
    assert headline.sentiment_status == "ok"


@respx.mock
async def test_compute_and_persist_sentiment_updates_story_aggregate(test_session_factory, openai_configured):
    async with test_session_factory() as session:
        story = Story(ticker="AAPL")
        session.add(story)
        await session.commit()
        story_id = story.id

    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-agg-1", story_id=story_id)
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-agg-2", story_id=story_id)
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=[
            _sentiment_response(80, "bullish", "First."),
            _sentiment_response(60, "routine", "Second."),
        ]
    )

    await compute_and_persist_sentiment("AAPL", test_session_factory)

    async with test_session_factory() as session:
        story = await session.get(Story, story_id)
    # First member: average = 80, count = 1. Second: 80 + (60-80)/2 = 70, count = 2.
    assert story.sentiment_score_count == 2
    assert story.sentiment_average == pytest.approx(70.0)


async def test_compute_and_persist_sentiment_skipped_when_not_configured(test_session_factory):
    # No respx mock registered at all -- a real HTTP attempt would raise a connection error.
    monkeypatch_value = settings.openai_api_key
    settings.openai_api_key = ""
    try:
        await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-skip")
        result = await compute_and_persist_sentiment("AAPL", test_session_factory)
    finally:
        settings.openai_api_key = monkeypatch_value

    assert result == {"status": "skipped"}
    async with test_session_factory() as session:
        headline = (await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-skip"))).scalar_one()
    assert headline.sentiment_status == "skipped"
    assert headline.sentiment_score is None


@respx.mock
async def test_compute_and_persist_sentiment_writes_error_status_on_failure(test_session_factory, openai_configured):
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-err")
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(401))

    result = await compute_and_persist_sentiment("AAPL", test_session_factory)

    assert result == {"status": "error"}
    async with test_session_factory() as session:
        headline = (await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-err"))).scalar_one()
    assert headline.sentiment_status == "error"
    assert headline.sentiment_score is None


@respx.mock
async def test_compute_and_persist_sentiment_retries_once_within_the_same_run(test_session_factory, openai_configured):
    """Distinct from test_..._retries_previously_errored_headline below: that one is about a *later*
    request retrying a headline that failed in some earlier run. This is the new same-run retry --
    one call fails, the very next attempt (same job, same headline) succeeds."""
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-transient")
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [httpx.Response(401), _sentiment_response(85, "bullish", "Recovered on retry.")]

    result = await compute_and_persist_sentiment("AAPL", test_session_factory)

    assert result == {"status": "ok"}
    assert route.call_count == 2
    async with test_session_factory() as session:
        headline = (
            await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-transient"))
        ).scalar_one()
    assert headline.sentiment_status == "ok"
    assert headline.sentiment_score == 85


@respx.mock
async def test_compute_and_persist_sentiment_gives_up_after_one_retry(test_session_factory, openai_configured):
    # Exactly one retry, not open-ended -- two failures in a row means the job gives up for this run.
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-perm-fail")
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [httpx.Response(401), httpx.Response(401)]

    result = await compute_and_persist_sentiment("AAPL", test_session_factory)

    assert result == {"status": "error"}
    assert route.call_count == 2
    async with test_session_factory() as session:
        headline = (
            await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-perm-fail"))
        ).scalar_one()
    assert headline.sentiment_status == "error"


@respx.mock
async def test_compute_and_persist_sentiment_processes_newest_headline_first(test_session_factory, openai_configured):
    now = datetime.now(timezone.utc)
    # Seeded oldest-to-newest on purpose -- proves the real query/ordering drives request order,
    # not insertion order (same "insert out of order" discipline as the Story-primary test).
    await _seed_headline_for_sentiment(
        test_session_factory, "AAPL", "https://example.com/order-old", title="Oldest", published_at=now - timedelta(hours=2)
    )
    await _seed_headline_for_sentiment(
        test_session_factory, "AAPL", "https://example.com/order-mid", title="Middle", published_at=now - timedelta(hours=1)
    )
    await _seed_headline_for_sentiment(
        test_session_factory, "AAPL", "https://example.com/order-new", title="Newest", published_at=now
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_sentiment_response(50, "routine", "Same for all.")
    )

    await compute_and_persist_sentiment("AAPL", test_session_factory)

    # Each outgoing request body embeds the headline's own title -- newest submitted first.
    bodies = [call.request.content.decode() for call in respx.calls]
    order = [next(t for t in ("Newest", "Middle", "Oldest") if t in body) for body in bodies]
    assert order == ["Newest", "Middle", "Oldest"]


@respx.mock
async def test_compute_and_persist_sentiment_retries_previously_errored_headline(test_session_factory, openai_configured):
    await _seed_headline_for_sentiment(test_session_factory, "AAPL", "https://example.com/sent-retry", sentiment_status="error")
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_sentiment_response(85, "bullish", "Recovered on retry.")
    )

    result = await compute_and_persist_sentiment("AAPL", test_session_factory)

    assert result == {"status": "ok"}
    async with test_session_factory() as session:
        headline = (await session.execute(select(Headline).where(Headline.url == "https://example.com/sent-retry"))).scalar_one()
    assert headline.sentiment_status == "ok"
    assert headline.sentiment_score == 85


@respx.mock
async def test_compute_and_persist_sentiment_excludes_errored_member_from_story_aggregate(test_session_factory, openai_configured):
    async with test_session_factory() as session:
        story = Story(ticker="AAPL")
        session.add(story)
        await session.commit()
        story_id = story.id

    await _seed_headline_for_sentiment(
        test_session_factory, "AAPL", "https://example.com/sent-mix-1", story_id=story_id, title="Good headline"
    )
    await _seed_headline_for_sentiment(
        test_session_factory, "AAPL", "https://example.com/sent-mix-2", story_id=story_id, title="Bad headline"
    )

    def _mixed_response(request: httpx.Request) -> httpx.Response:
        # Keyed on request content, not call order -- the two headlines run concurrently (and the
        # failing one now gets retried once too), so which physically arrives first isn't
        # guaranteed the way a plain sequential side_effect list would assume.
        if "Good headline" in request.content.decode():
            return _sentiment_response(75, "bullish", "Real score.")
        return httpx.Response(401)

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=_mixed_response)

    await compute_and_persist_sentiment("AAPL", test_session_factory)

    async with test_session_factory() as session:
        story = await session.get(Story, story_id)
    # The errored member never counted -- average is exactly the one real score, not skewed.
    assert story.sentiment_score_count == 1
    assert story.sentiment_average == pytest.approx(75.0)
