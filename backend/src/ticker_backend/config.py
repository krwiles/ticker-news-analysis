from datetime import timedelta
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    The same image runs as `ui`, `api`, or `worker` depending on `app_mode` —
    see docs/adr/0001-single-image-multi-mode-containers.md.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "api"
    database_url: str = "postgresql+asyncpg://ticker:ticker@db:5432/ticker"
    redis_url: str = "redis://redis:6379/0"
    # Standalone Milvus (spec 0002) -- worker-only, see docker-compose.yml for why.
    milvus_uri: str = "http://milvus:19530"
    # The ui and api containers are different origins -- only this one is allowed in (main.py's CORS).
    ui_origin: str = "http://localhost:3000"
    finnhub_api_key: str = ""
    # OpenAI's embeddings API (spec 0002 story-grouping, lesson 18) -- see ADR 0007.
    openai_api_key: str = ""
    # SEC requires a descriptive User-Agent identifying the app + a contact
    # email on every request — not a secret, just a compliance string.
    sec_edgar_user_agent: str = "TickerNewsAnalysis contact@example.com"
    # How long /api/search waits on the fetch job before treating it as a
    # complete failure — see ADR 0004 and spec 0001.
    job_timeout_seconds: int = 10
    # Cosine-similarity cutoff for Story matching -- see ADR 0011.
    story_similarity_threshold: float = 0.75


settings = Settings()

# How far back a search looks -- a fixed business rule (spec 0001). Lives here, not providers.py/
# search.py, so either can import it without pulling in the other's own import chain.
RECENT_HEADLINES_WINDOW = timedelta(days=7)

# Empirically tuned score-to-enum cutoffs -- see docs/plans/0026-*.md. Lives here for the same
# import-chain reason as RECENT_HEADLINES_WINDOW above.
SENTIMENT_NEGATIVE_MAX = 40
SENTIMENT_POSITIVE_MIN = 70


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
