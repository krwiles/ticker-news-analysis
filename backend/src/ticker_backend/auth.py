"""Google sign-in -- see docs/plans/0037-*.md, spec 0006, ADR 0016.

The frontend does the actual OAuth dance via Google Identity Services and hands this
module a signed ID token (a JWT, called a "credential" throughout, matching GIS's own
terminology). This module's whole job is: verify it, upsert a User, and manage an
opaque, Redis-backed session -- never a signed cookie (ADR 0016's revocability
argument) and never a second Redis pool (reuses app.state.arq_redis via search.py's
existing get_arq_redis dependency, since ArqRedis is a real redis.asyncio.Redis
subclass).
"""

import secrets
from datetime import datetime, timezone

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel

from ticker_backend.config import settings
from ticker_backend.models import User
from ticker_backend.search import get_arq_redis, get_session_factory

router = APIRouter()

# The cookie holds only this -- never session data itself (ADR 0016).
SESSION_COOKIE_NAME = "session_id"
# Sliding window, refreshed on every authenticated request -- long enough in practice to
# match spec 0006's "persists across browser restarts" (ADR 0016).
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


class TokenVerificationError(Exception):
    """Raised when a Google credential fails verification -- expired, wrong audience,
    bad signature, or any other reason it can't be trusted (ADR 0016)."""


class GoogleSignInRequest(BaseModel):
    credential: str


def _verify_google_credential(credential: str) -> dict:
    """The real verifier -- checks the ID token's signature against Google's own
    rotating public keys, plus issuer/audience/expiry (google-auth's job, not
    hand-rolled JWT/JWKS handling -- ADR 0016). Returns the token's claims dict.

    google-auth's own docstring for verify_oauth2_token names two distinct exception
    types for a bad token (ValueError, and GoogleAuthError for a wrong issuer
    specifically) -- both collapse to the same TokenVerificationError here, since the
    caller only needs to know "this credential can't be trusted", not why."""
    try:
        return id_token.verify_oauth2_token(credential, google_requests.Request(), settings.google_client_id)
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise TokenVerificationError(str(exc)) from exc


def get_token_verifier():
    """FastAPI dependency -- tests override this with a fake returning canned claims,
    matching get_arq_redis/get_session_factory's existing override pattern (search.py)
    so no test ever calls Google for real."""
    return _verify_google_credential


def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


async def _create_session(redis: ArqRedis, sub: str) -> str:
    """A fresh opaque id -> the signed-in user's sub, in Redis (ADR 0016)."""
    session_id = secrets.token_urlsafe(32)
    await redis.set(_session_key(session_id), sub, ex=SESSION_TTL_SECONDS)
    return session_id


async def _resolve_session(redis: ArqRedis, session_id: str) -> str | None:
    """Looks up a session id's owning sub, refreshing its TTL on every use -- the
    sliding window ADR 0016 describes, so an actively-used session never silently
    expires. Returns None for an unknown/expired id, never an error."""
    key = _session_key(session_id)
    sub = await redis.get(key)
    if sub is None:
        return None
    await redis.expire(key, SESSION_TTL_SECONDS)
    # redis-py hands back bytes unless decode_responses is set -- normalize either way.
    return sub.decode() if isinstance(sub, bytes) else sub


async def _delete_session(redis: ArqRedis, session_id: str) -> None:
    await redis.delete(_session_key(session_id))


async def _upsert_user(session, claims: dict) -> User:
    """Creates or refreshes a User row keyed on the token's `sub` claim (ADR 0016) --
    first-ever sign-in and every later one go through this identical path, no separate
    "new account" branch (spec 0006)."""
    user = await session.get(User, claims["sub"])
    if user is None:
        user = User(sub=claims["sub"])
        session.add(user)
    # Always overwritten from the token's claims -- spec 0006's read-only,
    # always-mirrors-Google requirement.
    user.email = claims.get("email")
    user.name = claims.get("name")
    user.picture_url = claims.get("picture")
    user.last_seen_at = datetime.now(timezone.utc)
    await session.flush()
    return user


def _user_to_dict(user: User) -> dict:
    return {"email": user.email, "name": user.name, "picture_url": user.picture_url}


@router.post("/api/auth/google")
async def sign_in_with_google(
    body: GoogleSignInRequest,
    response: Response,
    verify_token=Depends(get_token_verifier),
    session_factory=Depends(get_session_factory),
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> dict:
    # Reject up front -- an invalid credential must never create a session or a cookie.
    try:
        claims = verify_token(body.credential)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid credential") from exc

    # Upsert the User row from the token's claims (spec 0006's identical
    # first-sign-in-or-later path).
    async with session_factory() as session:
        user = await _upsert_user(session, claims)
        await session.commit()
        user_dict = _user_to_dict(user)

    # Create the Redis-backed session and hand the opaque id back as an HttpOnly cookie.
    session_id = await _create_session(arq_redis, user.sub)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return user_dict


@router.get("/api/auth/me")
async def me(
    request: Request,
    session_factory=Depends(get_session_factory),
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> dict:
    # No cookie, an unknown session id, and a session pointing at a deleted user all
    # collapse to the same signed-out shape -- spec 0006's "never a broken state".
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    sub = await _resolve_session(arq_redis, session_id) if session_id else None
    if sub is None:
        return {"user": None}

    async with session_factory() as session:
        user = await session.get(User, sub)
    if user is None:
        return {"user": None}
    return {"user": _user_to_dict(user)}


@router.post("/api/auth/logout")
async def logout(
    request: Request,
    response: Response,
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> dict:
    # Deletes the Redis key outright -- real revocation, not just an expiring cookie.
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await _delete_session(arq_redis, session_id)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}
