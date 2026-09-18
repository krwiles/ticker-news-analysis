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

# How far back a search looks -- a fixed business rule (spec 0001), not env-configurable, so a
# bare constant rather than a Settings field. Lives here, not search.py or providers.py, so
# either can import it without pulling the other's own import chain along (FastAPI vs. pymilvus)
# into a container mode that doesn't otherwise need it -- see providers.py's own comment on the
# pymilvus/dotenv landmine this avoids reintroducing.
RECENT_HEADLINES_WINDOW = timedelta(days=7)

# Empirically checked against 15 real headlines spanning clearly positive/negative/neutral
# content (lesson 26) -- a light-touch pass, not the full similarity-threshold treatment (a
# boundary here is a labeling nuance, not a correctness bug the way a wrongly-merged Story was).
# Real scores clustered cleanly: negative 15-34, neutral 50-68, positive 75-90 -- these cutoffs
# sit in the real gaps between those clusters. See docs/plans/0026-*.md for the full sample.
# Lives here (not providers.py) for the same reason RECENT_HEADLINES_WINDOW does -- search.py
# needs this too (lesson 28), and neither it nor providers.py should import from the other.
SENTIMENT_NEGATIVE_MAX = 40
SENTIMENT_POSITIVE_MIN = 70


def derive_sentiment_enum(score: int | float) -> Literal["positive", "neutral", "negative"]:
    """Always derived from the score, never asked of the model independently
    (spec 0005/ADR 0014) -- guarantees the enum and score can never disagree.
    Takes a float too -- a Story's own aggregate (lesson 28) is an average
    of integer scores, not necessarily an integer itself."""
    if score <= SENTIMENT_NEGATIVE_MAX:
        return "negative"
    if score >= SENTIMENT_POSITIVE_MIN:
        return "positive"
    return "neutral"
