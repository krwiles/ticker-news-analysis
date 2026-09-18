"""Computing and persisting Headline sentiment (spec 0005 / ADR 0014) -- the OpenAI sentiment
call, filing-content extraction, and the job that runs them across a ticker's pending Headlines.

Deliberately framework-agnostic, like providers.py: no ARQ `ctx`, no FastAPI. worker.py wraps
`compute_and_persist_sentiment` as `sentiment_job`.
"""

import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select, update

from ticker_backend.config import RECENT_HEADLINES_WINDOW, settings
from ticker_backend.db import async_session_factory
from ticker_backend.models import Headline, Story
from ticker_backend.providers import ProviderFetchError, embedding_input_text

log = structlog.get_logger()

# Cheapest chat-completion tier as of lesson 24 -- see ADR 0014. Re-verify before trusting this is
# still cheapest; pricing already moved once during that ADR's own research.
OPENAI_SENTIMENT_MODEL = "gpt-5-nano"

# Structured Outputs schema (spec 0005) guarantees this exact shape back, not free text to parse.
# gloss must never restate the enum itself ("positive") -- the prompt below is what prevents that.
_SENTIMENT_SYSTEM_PROMPT = (
    "Score this stock news headline from 0 (most negative) to 100 (most positive). "
    "Give a concise, natural one-word gloss describing the specific character of the "
    "news, such as bullish, reassuring, routine, speculative, operational, regulatory, "
    "concerning, or alarming. This list is illustrative, not a fixed vocabulary. "
    "Choose a different word when it is more precise, and never use positive, neutral, "
    "or negative as the gloss. Give a one-sentence rationale for the score."
)
_SENTIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "gloss": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["score", "gloss", "rationale"],
    "additionalProperties": False,
}


async def get_sentiment(text: str, client: httpx.AsyncClient) -> dict:
    """One headline's sentiment (spec 0005/ADR 0014) -- one call per headline, unlike
    get_embeddings' batching; Structured Outputs guarantees the {"score", "gloss", "rationale"}
    shape rather than parsing free text."""
    try:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": OPENAI_SENTIMENT_MODEL,
                "messages": [
                    {"role": "system", "content": _SENTIMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "sentiment", "strict": True, "schema": _SENTIMENT_SCHEMA},
                },
            },
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFetchError(f"OpenAI sentiment fetch failed: {exc}") from exc

    # Structured Outputs guarantees the schema, but the content is still a JSON *string* to parse.
    try:
        return json.loads(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise ProviderFetchError(f"OpenAI sentiment response missing data: {exc}") from exc


# ~20,000 tokens (ADR 0014), approximated as chars/4 -- a rough safety net, not a precision
# instrument, comfortably above every real MD&A section measured (4,500-12,000 tokens, 12 filers).
FILING_CONTENT_CAP_CHARS = 80_000

# The real title must follow "Item 7" -- a bare number alone matched a stray citation/TOC mention
# on real filers. Period optional -- one real filer (George Risk Industries) omits it.
_ITEM_7_HEADING_RE = re.compile(r"Item\s*7\.?\s*(?:Management|MANAGEMENT)", re.IGNORECASE)
# Same "real title must follow" discipline -- a bare "Item 8" alone matched a real filer's own
# inline cross-reference, cutting the section off after one sentence.
_NEXT_ITEM_HEADING_RE = re.compile(
    r"Item\s*7A\.?\s*(?:Quantitative|QUANTITATIVE)|Item\s*8\.?\s*(?:Financial|FINANCIAL)", re.IGNORECASE
)
# Catches a real case (Friedman Industries) where the MD&A isn't in the document at all, only a
# pointer to a separate exhibit -- confirmed silent on 11 other filers with inline MD&A.
_INCORPORATED_BY_REFERENCE_RE = re.compile(r"incorporated\s+(herein\s+)?by\s+reference", re.IGNORECASE)


def _strip_html_to_text(html: str) -> str:
    """Flattens raw filing HTML to plain text. Regex, not a real DOM parser -- proven reliable
    across 12 real filings; a parser is only needed for structural navigation, see ADR 0014."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_relevant_filing_section(text: str) -> str:
    """The real MD&A section when it's actually findable, else the whole
    document's start -- ADR 0014's two-tier design (structural anchor
    extraction was considered and dropped after a broader real sample
    showed it unreliable). Caps at FILING_CONTENT_CAP_CHARS either way."""
    matches = list(_ITEM_7_HEADING_RE.finditer(text))
    if matches:
        # Last match, not first -- skips the table of contents' own earlier listing.
        start = matches[-1].start()
        next_match = _NEXT_ITEM_HEADING_RE.search(text, start + 10)
        end = next_match.start() if next_match else len(text)
        section = text[start:end]
        # A heading with no real content behind it (MD&A incorporated by reference from an
        # exhibit) -- fall through to the whole document instead of a one-sentence pointer.
        if not _INCORPORATED_BY_REFERENCE_RE.search(section[:400]):
            return section[:FILING_CONTENT_CAP_CHARS]

    # No Item 7 at all (8-K/S-1/DEF 14A, or an unmatched 10-K/10-Q), or a reference-only
    # match above -- use the document from the start instead.
    return text[:FILING_CONTENT_CAP_CHARS]


async def get_filing_content(url: str, client: httpx.AsyncClient) -> str:
    """Fetches a real filing document and extracts its most sentiment-relevant
    content (spec 0005/ADR 0014), capped at FILING_CONTENT_CAP_CHARS."""
    try:
        response = await client.get(url, headers={"User-Agent": settings.sec_edgar_user_agent})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderFetchError(f"Filing content fetch failed: {exc}") from exc

    text = _strip_html_to_text(response.text)
    section = _extract_relevant_filing_section(text)
    # Log actual truncation for future recalibration -- same discipline
    # story_similarity_threshold's own empirical tuning already established.
    if len(section) >= FILING_CONTENT_CAP_CHARS:
        log.warning("sentiment.filing_content_capped", url=url, real_chars=len(text))
    return section


# ~500 tokens (ADR 0014), approximated as chars/4 -- real content runs ~55-135 tokens, so this
# is a safety net against a malformed provider field, not a limit meant to trigger normally.
NEWS_CONTENT_CAP_CHARS = 2_000

# A short pause before the automatic retry, giving a transient failure (real-world evidence:
# OpenAI timeouts under load) a moment to clear. Module-level so tests can monkeypatch it to 0.
SENTIMENT_RETRY_DELAY_SECONDS = 2.0

# Doubled from the original 10s -- live evidence showed every failure was a ReadTimeout, not a
# real rejection (OpenAI slow, not down). Not yet re-measured against a fresh sample.
SENTIMENT_HTTP_TIMEOUT_SECONDS = 20.0


async def _fetch_pending_headlines(ticker: str, session_factory) -> list[Headline]:
    """Every Headline in this ticker's recent window that doesn't have a real score yet --
    including previously skipped/errored ones, which is what makes retry work (spec 0005/ADR
    0014's own Non-goal: no dedicated backfill, only whatever a later request's own scope happens
    to include again). Newest first (spec 0005): the most recently published headlines are what a
    user actually came back to check, so they're worth resolving before older ones."""
    cutoff = datetime.now(timezone.utc) - RECENT_HEADLINES_WINDOW
    # Only a real score (`ok`) is permanent -- this WHERE clause is the entire enforcement of
    # that rule (spec 0005); `skipped`/`error` both stay eligible for retry.
    async with session_factory() as session:
        rows = await session.execute(
            select(Headline)
            .where(
                Headline.ticker == ticker,
                Headline.published_at >= cutoff,
                (Headline.sentiment_status.is_(None)) | (Headline.sentiment_status.in_(["skipped", "error"])),
            )
            .order_by(Headline.published_at.desc())
        )
        return list(rows.scalars())


async def _mark_skipped(headlines: list[Headline], session_factory) -> None:
    """Not configured -- write `skipped` explicitly rather than leaving these ambiguously NULL,
    same "explicit over ambiguous" discipline this schema already uses elsewhere."""
    async with session_factory() as session:
        ids = [h.id for h in headlines]
        await session.execute(update(Headline).where(Headline.id.in_(ids)).values(sentiment_status="skipped"))
        await session.commit()


async def _fetch_one(headline: Headline, client: httpx.AsyncClient) -> dict:
    # News uses title+summary (already free); filings need a real fetch+extraction (lesson 25).
    if headline.category == "filing":
        text = await get_filing_content(headline.url, client)
    else:
        text = embedding_input_text(headline.title, headline.summary)[:NEWS_CONTENT_CAP_CHARS]
    return await get_sentiment(text, client)


async def _fetch_with_retry(
    headline: Headline, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
) -> tuple[Headline, dict | None, ProviderFetchError | None]:
    """One automatic retry per headline -- OpenAI timeouts under load are usually transient, not
    permanent. The delay sits outside the semaphore, so a waiting retry frees its concurrency
    slot for another headline instead of holding it idle."""
    last_error: ProviderFetchError | None = None
    for attempt in range(2):
        if attempt > 0:
            await asyncio.sleep(SENTIMENT_RETRY_DELAY_SECONDS)
        try:
            async with semaphore:
                result = await _fetch_one(headline, client)
            return headline, result, None
        except ProviderFetchError as exc:
            last_error = exc
    return headline, None, last_error


async def _persist_result(
    headline: Headline, result: dict | None, error: ProviderFetchError | None, session
) -> None:
    """Writes one headline's outcome and, on success, folds it into its Story's running
    aggregate. Called once per headline as each attempt resolves, so a batch fills in
    incrementally (see compute_and_persist_sentiment) rather than all at once."""
    if error is not None:
        # error.__cause__ is the real underlying exception (from exc) -- a bare timeout's own
        # str() is empty, so without the type name a timeout looks identical to a real HTTP error.
        log.warning(
            "sentiment.sentiment_failed",
            headline_id=str(headline.id),
            error_type=type(error.__cause__ or error).__name__,
            error=str(error),
        )
        await session.execute(update(Headline).where(Headline.id == headline.id).values(sentiment_status="error"))
        await session.commit()
        return

    # A real score -- write it, along with the gloss/rationale that explain it.
    score = result["score"]
    await session.execute(
        update(Headline)
        .where(Headline.id == headline.id)
        .values(
            sentiment_score=score,
            sentiment_gloss=result["gloss"],
            sentiment_rationale=result["rationale"],
            sentiment_status="ok",
        )
    )

    # Only an `ok` member ever folds into the running average -- `skipped`/`error`
    # members are excluded entirely, never treated as zero (spec 0005's own Non-goal).
    if headline.story_id is not None:
        story = await session.get(Story, headline.story_id)
        story.record_sentiment(score)

    await session.commit()


async def compute_and_persist_sentiment(ticker: str, session_factory=async_session_factory) -> dict:
    """Computes and persists sentiment for whatever Headlines in this ticker's recent window
    don't have a real score yet (see _fetch_pending_headlines). Framework-agnostic, like
    fetch_and_persist_headlines -- worker.py wraps this as sentiment_job."""
    # Normalize so every downstream lookup/write uses the same casing.
    ticker = ticker.upper()

    # Find whatever's still pending for this ticker.
    pending_headlines = await _fetch_pending_headlines(ticker, session_factory)
    if not pending_headlines:
        return {"status": "ok"}

    # Dependency not configured -- mark everything skipped and stop, no network calls attempted.
    if not settings.openai_api_key:
        await _mark_skipped(pending_headlines, session_factory)
        return {"status": "skipped"}

    # Bounds true concurrency to what's verified safe (ADR 0014: 20 calls, 6.64s) -- unbounded,
    # 239 real headlines all timed out together as httpx's connection pool backed up under load.
    semaphore = asyncio.Semaphore(20)

    # Sequential writes avoid a lost update when two headlines share a Story. as_completed (not
    # gather) commits each result as soon as it resolves, so the frontend's poll sees it incrementally.
    any_error = False
    async with httpx.AsyncClient(timeout=SENTIMENT_HTTP_TIMEOUT_SECONDS) as client, session_factory() as session:
        tasks = [asyncio.ensure_future(_fetch_with_retry(h, client, semaphore)) for h in pending_headlines]
        for coro in asyncio.as_completed(tasks):
            headline, result, error = await coro
            any_error = any_error or error is not None
            await _persist_result(headline, result, error, session)

    return {"status": "error" if any_error else "ok"}
