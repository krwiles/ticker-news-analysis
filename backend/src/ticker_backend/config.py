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
    # Cosine-similarity cutoff for Story matching (spec 0002, ADR 0006) --
    # empirically tuned live against real headline pairs in lesson 19, not
    # guessed. See docs/adr/0011-milvus-story-collection-design.md.
    story_similarity_threshold: float = 0.75


settings = Settings()
