from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Agentic Database Discovery Platform"
    app_env: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    database_url: str

    azure_keyvault_url: str
    azure_keyvault_secret_name: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: SecretStr

    llm_model: str = "gpt-4o"
    llm_temperature: float = 0
    llm_max_retries: int = 2
    classification_confidence_threshold: float = Field(0.90, ge=0, le=1)
    hipaa_confidence_threshold: float = Field(0.85, ge=0, le=1)
    max_agent_concurrency: int = Field(3, ge=1, le=20)


@lru_cache
def get_settings() -> Settings:
    return Settings()
