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


settings = Settings()
