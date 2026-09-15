"""Shared test fixtures. See docs/plans/0010-testing-search-feature.md.

Tests run on the host (via `uv run pytest`), same as `dbmate` itself --
never inside a container -- so everything here talks to Postgres/Redis via
`localhost`, not the `db`/`redis` compose network names.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# dbmate's own scheme (postgres://...?sslmode=disable) -- reused for the
# SQLAlchemy/asyncpg engine below by swapping the scheme and dropping the
# query string, which asyncpg doesn't need locally.
TEST_DBMATE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgres://ticker:ticker@localhost:5432/ticker_test?sslmode=disable"
)
TEST_ASYNC_URL = TEST_DBMATE_URL.replace("postgres://", "postgresql+asyncpg://", 1).split("?")[0]


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    """Runs once per test session -- creates ticker_test if missing, applies
    every migration. Same migration files as dev (ADR 0005): no separate,
    hand-maintained test schema to let drift out of sync."""
    subprocess.run(
        ["dbmate", "--url", TEST_DBMATE_URL, "up"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def test_session_factory():
    """Function-scoped, not session-scoped: an async engine is bound to the
    event loop it was created on, and pytest-asyncio gives each test
    function its own loop by default -- a session-scoped engine gets
    orphaned across test boundaries ("Event loop is closed" on cleanup).
    Recreating it per test is cheap at this data size and avoids fighting
    pytest-asyncio's loop-scope configuration entirely."""
    engine = create_async_engine(TEST_ASYNC_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _clean_tables(test_session_factory):
    """Truncates before each test rather than wrapping in a rolled-back
    transaction -- simpler with async SQLAlchemy, and cheap at this data
    size (persist-and-truncate, not drop/recreate every run)."""
    async with test_session_factory() as session:
        # All three in one statement, not sequential TRUNCATEs -- headlines
        # and stories now reference each other (a real circular FK, ADR
        # 0009), and Postgres refuses to truncate either alone without the
        # other in the same statement.
        await session.execute(text("TRUNCATE TABLE headlines, companies, stories"))
        await session.commit()
    yield
