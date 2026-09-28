from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# Where Docker Compose mounts file-based secrets inside a container (ADR 0017).
SECRETS_DIR = "/run/secrets"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    The same image runs as `ui`, `api`, or `worker` depending on `app_mode` —
    see docs/adr/0001-single-image-multi-mode-containers.md.
    """

    # None off-container (no /run/secrets) -- avoids pydantic-settings' missing-directory warning.
    model_config = SettingsConfigDict(
        env_file=".env",
        secrets_dir=SECRETS_DIR if Path(SECRETS_DIR).is_dir() else None,
        extra="ignore",
    )

    app_mode: str = "api"
    # The DSN is assembled from these parts (see database_url) so the password can arrive as a file secret.
    postgres_user: str = "ticker"
    postgres_db: str = "ticker"
    postgres_host: str = "db"
    postgres_password: str = ""
    redis_url: str = "redis://redis:6379/0"
    # Standalone Milvus (spec 0002) -- worker-only, see docker-compose.yml for why.
    milvus_uri: str = "http://milvus:19530"
    # The ui and api containers are different origins -- only this one is allowed in (main.py's CORS).
    ui_origin: str = "http://localhost:3000"
    # Secrets below (and postgres_password) come from /run/secrets files -- see ADR 0017.
    finnhub_api_key: str = ""
    # OpenAI's embeddings API (spec 0002 story-grouping, lesson 18) -- see ADR 0007.
    openai_api_key: str = ""
    # api never holds the OpenAI key (least privilege) -- it gets this non-secret mirror instead.
    sentiment_configured: bool = False
    # SEC requires a descriptive User-Agent identifying the app + a contact
    # email on every request — not a secret, just a compliance string.
    sec_edgar_user_agent: str = "TickerNewsAnalysis contact@example.com"
    # How long /api/search waits on the fetch job before treating it as a
    # complete failure — see ADR 0004 and spec 0001.
    job_timeout_seconds: int = 10
    # Cosine-similarity cutoff for Story matching -- see ADR 0011.
    story_similarity_threshold: float = 0.75
    # Not a secret -- GIS's credential flow never exchanges a client secret (ADR 0016).
    google_client_id: str = ""
    # Environment-driven -- True over plain HTTP makes the browser refuse the cookie (ADR 0016).
    cookie_secure: bool = False

    @property
    def database_url(self) -> URL:
        """A SQLAlchemy URL object, not a string -- URL.create escapes special characters in the password."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=5432,
            database=self.postgres_db,
        )


settings = Settings()

# Secrets each mode cannot run without -- the OpenAI key is deliberately absent (spec 0005 degrades without it).
REQUIRED_SECRETS_BY_MODE = {
    "ui": [],
    "api": ["postgres_password"],
    "worker": ["postgres_password", "finnhub_api_key"],
}


def require_secrets(cfg: Settings) -> None:
    """Fail fast at startup, naming what's missing (never its value). Called from create_app() and the
    worker's startup hook, not Settings itself -- Settings() builds at import time, and tests import with no secrets."""
    # An unrecognized mode must not silently pass as "needs nothing" -- worker has no other guard like this.
    if cfg.app_mode not in REQUIRED_SECRETS_BY_MODE:
        raise RuntimeError(f"Unrecognized APP_MODE {cfg.app_mode!r} -- expected one of {list(REQUIRED_SECRETS_BY_MODE)}.")
    # Collect every required secret for this mode that is empty.
    missing = [name for name in REQUIRED_SECRETS_BY_MODE[cfg.app_mode] if not getattr(cfg, name)]
    # Refuse to start with a clear, actionable message instead of failing later on an opaque auth error.
    if missing:
        raise RuntimeError(
            f"APP_MODE={cfg.app_mode!r} is missing required secret(s): {', '.join(missing)}. "
            "Run scripts/init-secrets.sh to create them (see README, ADR 0017)."
        )

# How far back a search looks -- a fixed business rule (spec 0001). Lives here, not providers.py/
# search.py, so either can import it without pulling in the other's own import chain.
RECENT_HEADLINES_WINDOW = timedelta(days=7)

# Empirically tuned score-to-enum cutoffs -- see docs/plans/0026-*.md. Lives here for the same
# import-chain reason as RECENT_HEADLINES_WINDOW above.
SENTIMENT_NEGATIVE_MAX = 40
SENTIMENT_POSITIVE_MIN = 70


def recent_headlines_cutoff(now: datetime) -> datetime:
    """The earliest published_at a headline can have and still count as "recent" -- aligned to the
    start of the oldest included UTC day, not an exact instant, so it can never fall inside the
    same-day granularity gap Finnhub's own from/to date range fetches by (providers.py, docs/plans/
    0039-*.md). `now` is a parameter, not datetime.now() called internally, matching
    build_daily_view's own testable-purity style (search.py)."""
    oldest_day = (now - RECENT_HEADLINES_WINDOW).date()
    return datetime.combine(oldest_day, time.min, tzinfo=timezone.utc)


def derive_sentiment_enum(score: int | float) -> Literal["positive", "neutral", "negative"]:
    """Always derived from the score, never asked of the model independently
    (spec 0005/ADR 0014) -- guarantees the enum and score can never disagree.
    Takes a float too -- a Story's own aggregate (lesson 28) is an average
    of integer scores, not necessarily an integer itself."""
    # Below the negative cutoff -- negative.
    if score <= SENTIMENT_NEGATIVE_MAX:
        return "negative"
    # At or above the positive cutoff -- positive.
    if score >= SENTIMENT_POSITIVE_MIN:
        return "positive"
    # Everything in between -- neutral.
    return "neutral"
