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

    # M1: auth + identity
    session_encryption_key: str = Field("", alias="SESSION_ENCRYPTION_KEY")
    entra_tenant_id: str = Field("", alias="ENTRA_TENANT_ID")
    entra_tenant_subdomain: str = Field("", alias="ENTRA_TENANT_SUBDOMAIN")
    entra_client_id: str = Field("", alias="ENTRA_CLIENT_ID")
    entra_client_secret: str = Field("", alias="ENTRA_CLIENT_SECRET")
    frontend_base_url: str = Field("http://localhost:3000", alias="FRONTEND_BASE_URL")
    api_base_url: str = Field("http://localhost:8000", alias="API_BASE_URL")

    # Blob storage
    blob_endpoint: str = Field("", alias="BLOB_ENDPOINT")
    blob_container_avatars: str = Field("avatars", alias="BLOB_CONTAINER_AVATARS")
    blob_container_pdfs: str = Field("pdfs", alias="BLOB_CONTAINER_PDFS")
    blob_container_raw: str = Field("raw", alias="BLOB_CONTAINER_RAW")
    blob_container_summaries: str = Field("summaries", alias="BLOB_CONTAINER_SUMMARIES")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def search_deployment(self) -> str:
        return self.azure_openai_deployment_search or self.azure_openai_deployment


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
