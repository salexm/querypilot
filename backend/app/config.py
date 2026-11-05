from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings read from environment variables.

    The API gets only the read-only database role. Admin and app credentials
    are deliberately absent, so generated SQL can't reach them.
    """

    postgres_host: str = "db"
    postgres_port: int = 5432
    analytics_db_name: str
    analytics_readonly_user: str
    analytics_readonly_password: SecretStr

    query_timeout_ms: int = 10_000
    query_max_rows: int = 1_000

    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_api_key: SecretStr = SecretStr("")
    llm_effort: str = "medium"
    llm_timeout_seconds: float = 60.0

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
