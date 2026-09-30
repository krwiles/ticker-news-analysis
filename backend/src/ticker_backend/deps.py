"""Shared FastAPI dependencies with no business logic of their own.

Broken out of search.py (ADR 0019): auth.py already depended on search.py's
get_arq_redis/get_session_factory, and watchlists needed search.py to depend on auth.py's
optional_user right back -- a real cycle. Both sides depending on this module instead,
which depends on neither, breaks it.
"""

from arq import ArqRedis
from fastapi import Request

from ticker_backend.db import async_session_factory


async def get_arq_redis(request: Request) -> ArqRedis:
    """FastAPI dependency -- real requests get api_lifespan's pool (search.py); tests
    override this to avoid needing a real Redis connection for endpoint tests that don't
    care about the job layer."""
    return request.app.state.arq_redis


def get_session_factory():
    """FastAPI dependency, not a plain default -- FastAPI introspects path operation
    parameters, and a bare async_sessionmaker breaks that. Depends() injects it without
    being treated as request data."""
    return async_session_factory
