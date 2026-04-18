from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_endpoint: str = Field(..., alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(..., alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str = Field("2025-03-01-preview", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_deployment: str = Field("gpt-5.3-chat", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_deployment_search: str | None = Field(
        None, alias="AZURE_OPENAI_DEPLOYMENT_SEARCH"
    )

    database_url: str = Field(
        "postgresql://postgres:postgres@localhost:5432/startup_analyzer",
        alias="DATABASE_URL",
    )
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    backend_host: str = Field("0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(8000, alias="BACKEND_PORT")
    cors_origins: str = Field("http://localhost:3000", alias="CORS_ORIGINS")

    agent_timeout_seconds: int = 90
    agent_max_retries: int = 3
    research_concurrency: int = Field(4, alias="RESEARCH_CONCURRENCY")

    # Observability
    log_dir: str = Field("./logs", alias="LOG_DIR")
    log_raw_responses: bool = Field(True, alias="LOG_RAW_RESPONSES")
    log_idea_text: bool = Field(False, alias="LOG_IDEA_TEXT")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def search_deployment(self) -> str:
        return self.azure_openai_deployment_search or self.azure_openai_deployment


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
