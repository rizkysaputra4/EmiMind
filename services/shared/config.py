"""Centralized application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoleConfig(BaseModel):
    provider: Literal["anthropic", "openai", "openai_compat", "google", "cli_agent", "fake"]
    model: str
    api_key: SecretStr
    base_url: str | None = None
    max_output_tokens: int = 1024
    timeout_s: int = 30


class Settings(BaseSettings):
    """EmiMind global settings model with EMI_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="EMI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: str = Field(
        default="dev", description="Application environment: dev, test, staging, prod"
    )
    env: str = Field(default="dev", alias="env")

    # Postgres
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://emimind:emimind@localhost:5432/emimind",
        description="Async connection string for SQLAlchemy/asyncpg",
    )
    postgres_dsn_sync: str = Field(
        default="postgresql://emimind:emimind@localhost:5432/emimind",
        description="Sync connection string for migrations/scripts",
    )

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_secure: bool = False
    minio_bucket_raw: str = "emimind-raw"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Global LLM Mode (can be 'live' or 'fake')
    llm_mode: str = "live"

    # LLM Reasoner Slot
    llm_reasoner_provider: Literal[
        "anthropic", "openai", "openai_compat", "google", "cli_agent", "fake"
    ] = "anthropic"
    llm_reasoner_model: str = "claude-sonnet-4-6"
    llm_reasoner_api_key: SecretStr = SecretStr("")
    llm_reasoner_base_url: str | None = None
    llm_reasoner_max_output_tokens: int = 1024
    llm_reasoner_timeout_s: int = 30

    # LLM Utility Slot
    llm_utility_provider: Literal[
        "anthropic", "openai", "openai_compat", "google", "cli_agent", "fake"
    ] = "anthropic"
    llm_utility_model: str = "claude-haiku-4-5-20251001"
    llm_utility_api_key: SecretStr = SecretStr("")
    llm_utility_base_url: str | None = None
    llm_utility_max_output_tokens: int = 512
    llm_utility_timeout_s: int = 15

    # LLM Judge Slot (Optional)
    llm_judge_provider: str | None = None
    llm_judge_model: str | None = None
    llm_judge_api_key: SecretStr = SecretStr("")
    llm_judge_base_url: str | None = None

    # Embeddings & Retrieval
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Chat Budget
    chat_token_budget: int = 7200

    def llm_role(self, role: Literal["reasoner", "utility", "judge"]) -> RoleConfig:
        """Constructs RoleConfig for specified LLM role with fallback handling."""
        p = getattr(self, f"llm_{role}_provider", "anthropic")
        api_key_val: SecretStr = getattr(self, f"llm_{role}_api_key", SecretStr(""))
        key_str = api_key_val.get_secret_value()

        if (
            self.llm_mode == "fake"
            or not key_str
            or key_str.startswith("sk-ant-test")
            or "mock" in key_str.lower()
            or key_str == "fake"
        ):
            return RoleConfig(
                provider="fake",
                model=f"fake-{role}",
                api_key=SecretStr("fake"),
                max_output_tokens=1024,
                timeout_s=10,
            )

        if role == "judge" and not self.llm_judge_provider:
            return self.llm_role("reasoner")

        return RoleConfig(
            provider=p,
            model=getattr(self, f"llm_{role}_model"),
            api_key=api_key_val,
            base_url=getattr(self, f"llm_{role}_base_url"),
            max_output_tokens=getattr(self, f"llm_{role}_max_output_tokens", 1024),
            timeout_s=getattr(self, f"llm_{role}_timeout_s", 30),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns cached Settings singleton."""
    return Settings()
