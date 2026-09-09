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


class Headline(Base):
    """One piece of tracked news content about a Ticker — see CONTEXT.md.

    `sentiment` fields aren't here yet on purpose: spec 0001 doesn't need
    them, spec 0002 will add them in their own migration when that feature
    actually starts.
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
    raw_content: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"Headline(ticker={self.ticker!r}, category={self.category!r}, title={self.title!r})"
