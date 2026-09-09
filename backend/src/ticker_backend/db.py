"""Shared async SQLAlchemy setup — the engine, session factory, and declarative
base every model maps onto. `health.py` creates its own throwaway engine for a
single `SELECT 1`; anything that needs real ORM sessions (models, queries)
goes through here instead.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ticker_backend.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Every mapped model inherits from this — see models.py."""
