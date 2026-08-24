from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables
    and the local .env file.

    Source database passwords are encrypted before being stored in
    PostgreSQL. The encryption key itself remains in the local .env
    file and must never be committed to Git.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================================
    # Application
    # ============================================================

    app_name: str = "Agentic Database Discovery Platform"
    app_env: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # ============================================================
    # PostgreSQL metadata store
    # ============================================================

    database_url: str

    # ============================================================
    # Temporary source-credential encryption
    # ============================================================

    source_credential_encryption_key: SecretStr

    # ============================================================
    # Azure Key Vault authentication
    # Used for retrieving the OpenAI API key
    # ============================================================

    azure_keyvault_url: str
    azure_keyvault_secret_name: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: SecretStr

    # ============================================================
    # LLM configuration
    # ============================================================

    llm_model: str = "gpt-4o"

    llm_temperature: float = Field(
        default=0,
        ge=0,
        le=2,
    )

    llm_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
    )

    llm_timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
    )

    # ============================================================
    # Classification configuration
    # ============================================================

    classification_batch_size: int = Field(
        default=40,
        ge=1,
        le=100,
    )

    classification_confidence_threshold: float = Field(
        default=0.90,
        ge=0,
        le=1,
    )

    classification_agent_version: str = (
        "classification-agent-v1"
    )

    # ============================================================
    # HIPAA configuration
    # ============================================================

    hipaa_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )

    hipaa_confidence_threshold: float = Field(
        default=0.85,
        ge=0,
        le=1,
    )

    hipaa_agent_version: str = "hipaa-agent-v1"

    # ============================================================
    # HIPAA deterministic scoring
    # ============================================================

    hipaa_score_policy_version: str = "hipaa-score-v1"

    hipaa_score_good: float = Field(
        default=100,
        ge=0,
        le=100,
    )

    hipaa_score_needs_review: float = Field(
        default=70,
        ge=0,
        le=100,
    )

    hipaa_score_serious: float = Field(
        default=35,
        ge=0,
        le=100,
    )

    hipaa_score_critical: float = Field(
        default=0,
        ge=0,
        le=100,
    )

    # ============================================================
    # Profiling configuration
    # ============================================================

    profile_sample_size: int = Field(
        default=3,
        ge=0,
        le=3,
    )

    profile_query_timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=3600,
    )

    profile_max_tables: int = Field(
        default=20,
        ge=1,
    )

    profile_max_columns_per_table: int = Field(
        default=100,
        ge=1,
    )

    mask_sensitive_samples: bool = True
    persist_raw_sample_values: bool = False

    # ============================================================
    # Dependency Mapping configuration
    # ============================================================

    dependency_confidence_threshold: float = Field(
        default=0.80,
        ge=0,
        le=1,
    )

    # ============================================================
    # Discovery orchestration
    # ============================================================

    max_agent_concurrency: int = Field(
        default=3,
        ge=1,
        le=20,
    )

    discovery_stage_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
    )

    discovery_stage_retry_delay_seconds: int = Field(
        default=5,
        ge=0,
        le=300,
    )

    discovery_read_only: bool = True
    discovery_run_history_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """
    Load and cache non-rotating application configuration.

    Retrieved OpenAI keys and source database passwords are not
    stored in this Settings object.
    """

    return Settings()