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

from sqlalchemy import DateTime, Text, func, text
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

    `sentiment` deliberately not here yet -- pushed to a later spec.

    `story_id` is nullable for now -- ADR 0009's eventual NOT NULL design,
    tightened once real matching logic populates it on every insert path.
    """

    __tablename__ = "headlines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, unique=True)
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

    def __repr__(self) -> str:
        return f"Headline(ticker={self.ticker!r}, category={self.category!r}, title={self.title!r})"


class Story(Base):
    """The event Headlines can share on a given day — see CONTEXT.md.
    No stored primary reference: it's always the earliest-published
    member, found via `ORDER BY published_at ASC LIMIT 1` — see ADR 0009."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"Story(ticker={self.ticker!r})"
