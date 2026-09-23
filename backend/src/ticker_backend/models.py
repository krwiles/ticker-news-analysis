"""ORM models — see CONTEXT.md for the entity definitions these map onto.

The table itself is owned by dbmate (db/migrations/), not by SQLAlchemy: these
classes describe the shape Python code reads/writes, they don't create or
alter anything. Keeping the two in sync by hand is the trade-off of using a
plain-SQL migration tool instead of one (like Alembic) that generates
migrations from the models.
"""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Float, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ticker_backend.db import Base


class Company(Base):
    """The persisted record a Ticker identifies — see CONTEXT.md.

    `cik`/`company_name` are nullable and that's deliberate: a row only ever
    gets created once some provider has confirmed the ticker is real (see
    providers.py's sequencing), and a null cik means "Finnhub covers this
    ticker but SEC's own mapping doesn't" — a real, permanent state, not a
    placeholder waiting to be backfilled.
    """

    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    cik: Mapped[str | None] = mapped_column(Text, default=None)
    company_name: Mapped[str | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"Company(ticker={self.ticker!r}, cik={self.cik!r}, company_name={self.company_name!r})"


class Headline(Base):
    """One piece of tracked news content about a Ticker — see CONTEXT.md.

    `story_id` is nullable for now -- ADR 0009's eventual NOT NULL design,
    tightened once real matching logic populates it on every insert path.

    Sentiment columns (spec 0005 / ADR 0014) are all nullable, no backfill --
    `NULL` means "not yet attempted", same staged-rollout pattern
    `outlet`/`summary`/`story_id` already used. No stored enum column: the
    `positive`/`neutral`/`negative` value is derived from `sentiment_score`
    at read time, never stored (ADR 0009's own derive-don't-store
    precedent). `sentiment_status` (`ok`/`skipped`/`error`) is distinct
    from a bare `NULL` -- see ADR 0014 for why that distinction matters.
    """

    __tablename__ = "headlines"
    # A shared article can belong to more than one ticker's feed (plan 0035) -- dedup is
    # per-ticker, not global, so this is a composite constraint, not a bare column-level unique=True.
    __table_args__ = (UniqueConstraint("ticker", "url"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    category: Mapped[Literal["news", "filing"]] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    outlet: Mapped[str | None] = mapped_column(Text, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    raw_content: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    sentiment_score: Mapped[int | None] = mapped_column(Integer, default=None)
    sentiment_gloss: Mapped[str | None] = mapped_column(Text, default=None)
    sentiment_rationale: Mapped[str | None] = mapped_column(Text, default=None)
    sentiment_status: Mapped[Literal["ok", "skipped", "error"] | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"Headline(ticker={self.ticker!r}, category={self.category!r}, title={self.title!r})"


class Story(Base):
    """The event Headlines can share on a given day — see CONTEXT.md.
    No stored primary reference: it's always the earliest-published
    member, found via `ORDER BY published_at ASC LIMIT 1` — see ADR 0009.

    `sentiment_average`/`sentiment_score_count` (spec 0005 / ADR 0014) are
    an incrementally-updated running average, not a live `AVG(...)` query --
    a deliberate exception to this class's own no-redundant-state precedent
    (see ADR 0014). Only members that reach `sentiment_status = 'ok'` ever
    count -- `skipped`/`error` members are excluded entirely, never treated
    as zero.
    """

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text)
    sentiment_average: Mapped[float | None] = mapped_column(Float, default=None)
    sentiment_score_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    def __repr__(self) -> str:
        return f"Story(ticker={self.ticker!r})"

    def record_sentiment(self, score: int) -> None:
        """Folds one more real member's score into the running average (spec 0005 / ADR 0014)
        -- only ever called for an `ok` member, so `skipped`/`error` scores never reach here."""
        if self.sentiment_score_count == 0:
            # First real member -- no prior average to update from.
            self.sentiment_average = float(score)
        else:
            # Fold the new score into the running average without storing every past score.
            new_count = self.sentiment_score_count + 1
            self.sentiment_average += (score - self.sentiment_average) / new_count
        self.sentiment_score_count += 1
