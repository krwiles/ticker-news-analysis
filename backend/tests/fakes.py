"""Shared fake pieces reused across test files -- extracted after four separate test files each
re-implemented the same get/set/incr/expire logic (docs/plans/0042-*.md's own review finding)."""

from httpx import AsyncClient

from ticker_backend.auth import SESSION_COOKIE_NAME


class FakeRedisKV:
    """get/set/incr/expire against a real in-memory dict, returning bytes like the real redis-py
    client does (ADR 0016) -- a missing fake here is exactly what let a real bug (rate_limit.py's
    datetime.fromisoformat() choking on bytes) through every test while it broke in production
    (docs/plans/0042-*.md)."""

    def __init__(self):
        self.kv: dict[str, bytes] = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = str(value).encode()

    async def incr(self, key):
        self.kv[key] = str(int(self.kv.get(key, b"0")) + 1).encode()
        return int(self.kv[key])

    async def expire(self, key, seconds):
        # TTL isn't modeled -- every current caller only cares about the counted/stored value.
        pass


async def sign_in(client: AsyncClient, redis: FakeRedisKV, sub: str) -> None:
    """A direct Redis write, matching auth.py's own session:{id} -> sub shape -- not a full
    Google sign-in round trip. Extracted after test_search_endpoint.py and
    test_watchlist_endpoint.py each reimplemented this identically (ADR 0019's own review)."""
    session_id = f"test-session-{sub}"
    await redis.set(f"session:{session_id}", sub)
    client.cookies.set(SESSION_COOKIE_NAME, session_id)
