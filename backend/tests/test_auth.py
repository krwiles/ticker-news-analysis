"""Tests for the Google sign-in endpoints -- see docs/plans/0037-*.md and ADR 0016.

Both get_token_verifier and get_arq_redis are overridden: this tests the endpoints' own
upsert/session logic, never a real Google credential or a real Redis connection. Mirrors
test_search_endpoint.py's dependency-override + fake-object shape.
"""

from unittest.mock import patch

import pytest
from google.auth import exceptions as google_auth_exceptions

from ticker_backend.auth import (
    SESSION_COOKIE_NAME,
    TokenVerificationError,
    _verify_google_credential,
    get_token_verifier,
)
from ticker_backend.main import app
from ticker_backend.models import User
from ticker_backend.search import get_arq_redis, get_session_factory
from httpx import ASGITransport, AsyncClient


class _FakeRedis:
    """Stands in for ArqRedis's plain redis.asyncio.Redis surface (ADR 0016) -- a real
    in-memory dict, not canned responses, so the session helpers' get/set/expire/delete
    calls behave like the real thing well enough to test against directly."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def expire(self, key, seconds):
        # TTL isn't modeled here -- these tests only care about presence/absence.
        pass

    async def delete(self, key):
        self.store.pop(key, None)


def _fake_verifier(claims: dict):
    # Stands in for get_token_verifier's real Google call -- always returns the given
    # claims, no network involved.
    def verify(credential: str) -> dict:
        return claims

    return verify


def _rejecting_verifier():
    # Stands in for a credential that fails Google's own verification (expired,
    # wrong audience, bad signature -- ADR 0016).
    def verify(credential: str) -> dict:
        raise TokenVerificationError("bad credential")

    return verify


@pytest.mark.parametrize(
    "raised",
    [ValueError("Token expired"), google_auth_exceptions.GoogleAuthError("Wrong issuer")],
)
def test_verify_google_credential_translates_both_real_failure_types(raised):
    # Arrange: google-auth's own verify_oauth2_token docs name two distinct exception
    # types for a bad token -- both must collapse to this module's own error type.
    with patch("ticker_backend.auth.id_token.verify_oauth2_token", side_effect=raised):
        # Act / Assert.
        with pytest.raises(TokenVerificationError):
            _verify_google_credential("irrelevant-credential")


async def test_google_sign_in_creates_new_user_on_first_credential(test_session_factory):
    # Arrange: a fake verifier standing in for a real, never-before-seen Google sub.
    redis = _FakeRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    app.dependency_overrides[get_token_verifier] = lambda: _fake_verifier(
        {"sub": "google-1", "email": "a@example.com", "name": "Ada", "picture": "https://img/a.png"}
    )
    try:
        # Act: sign in with the fake credential.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/google", json={"credential": "fake-jwt"})
    finally:
        app.dependency_overrides.clear()

    # Assert: a real row was created, the response reflects it, and a session cookie was set.
    assert response.status_code == 200
    assert response.json() == {"email": "a@example.com", "name": "Ada", "picture_url": "https://img/a.png"}
    assert SESSION_COOKIE_NAME in response.cookies
    async with test_session_factory() as session:
        user = await session.get(User, "google-1")
    assert user is not None and user.email == "a@example.com"


async def test_google_sign_in_overwrites_existing_user_without_a_second_row(test_session_factory):
    # Arrange: sign in once, then again with the same sub but changed name/picture.
    redis = _FakeRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            app.dependency_overrides[get_token_verifier] = lambda: _fake_verifier(
                {"sub": "google-1", "email": "a@example.com", "name": "Ada", "picture": "https://img/old.png"}
            )
            # Act: first sign-in.
            await client.post("/api/auth/google", json={"credential": "fake-jwt-1"})
            app.dependency_overrides[get_token_verifier] = lambda: _fake_verifier(
                {"sub": "google-1", "email": "a@example.com", "name": "Ada Lovelace", "picture": "https://img/new.png"}
            )
            # Act: second sign-in, same Google sub, Google-side name/picture changed.
            response = await client.post("/api/auth/google", json={"credential": "fake-jwt-2"})
    finally:
        app.dependency_overrides.clear()

    # Assert: the row was refreshed in place, not duplicated.
    assert response.json() == {"email": "a@example.com", "name": "Ada Lovelace", "picture_url": "https://img/new.png"}
    async with test_session_factory() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(User).where(User.sub == "google-1"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].name == "Ada Lovelace"


async def test_google_sign_in_rejects_invalid_credential(test_session_factory):
    # Arrange: a verifier that always raises, like a real expired/forged credential would.
    redis = _FakeRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    app.dependency_overrides[get_token_verifier] = _rejecting_verifier
    try:
        # Act.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/google", json={"credential": "not-a-real-jwt"})
    finally:
        app.dependency_overrides.clear()

    # Assert: rejected, no session cookie, and no Redis session key was ever created.
    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies
    assert redis.store == {}


async def test_me_with_no_cookie_returns_signed_out(test_session_factory):
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeRedis()
    try:
        # Act: no cookie at all -- a first-ever visit.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.clear()

    # Assert: signed-out shape, not an error (spec 0006's "never a broken page").
    assert response.status_code == 200
    assert response.json() == {"user": None}


async def test_me_with_unknown_session_id_returns_signed_out(test_session_factory):
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeRedis()
    try:
        # Act: a cookie present, but its session id was never actually issued (expired/revoked).
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE_NAME, "never-issued")
            response = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.clear()

    # Assert: collapses to the same signed-out shape as no cookie at all.
    assert response.status_code == 200
    assert response.json() == {"user": None}


async def test_me_with_valid_session_returns_the_signed_in_user(test_session_factory):
    redis = _FakeRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    app.dependency_overrides[get_token_verifier] = lambda: _fake_verifier(
        {"sub": "google-1", "email": "a@example.com", "name": "Ada", "picture": "https://img/a.png"}
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Arrange: a real sign-in, giving the client a real session cookie.
            await client.post("/api/auth/google", json={"credential": "fake-jwt"})
            # Act: a later request, cookie carried automatically by the client's own jar.
            response = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.clear()

    # Assert: resolves back to the same real user.
    assert response.status_code == 200
    assert response.json() == {"user": {"email": "a@example.com", "name": "Ada", "picture_url": "https://img/a.png"}}


async def test_logout_deletes_the_redis_session_key(test_session_factory):
    redis = _FakeRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    app.dependency_overrides[get_token_verifier] = lambda: _fake_verifier(
        {"sub": "google-1", "email": "a@example.com", "name": "Ada", "picture": "https://img/a.png"}
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Arrange: a real sign-in creates a real key in the fake Redis store.
            await client.post("/api/auth/google", json={"credential": "fake-jwt"})
            assert len(redis.store) == 1
            # Act.
            response = await client.post("/api/auth/logout")
    finally:
        app.dependency_overrides.clear()

    # Assert: the key itself is gone from Redis -- real revocation, not just an expiring
    # cookie -- verified directly against the store, not just the response.
    assert response.status_code == 200
    assert redis.store == {}
