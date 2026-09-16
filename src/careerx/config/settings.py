"""Application configuration.

All runtime knobs are environment driven so the same image can run locally,
in CI and on a free-tier host without code changes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["gemini", "openai"]
EmbeddingBackendName = Literal["auto", "provider", "sentence-transformers", "hashing"]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment / ``.env``."""

    # ------------------------------------------------------------------
    # LLM provider
    # ------------------------------------------------------------------
    llm_provider: ProviderName = "gemini"

    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "text-embedding-004"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_base_url: str | None = None

    temperature: float = 0.2
    max_retries: int = Field(default=3, ge=1, le=10)
    request_timeout_seconds: float = Field(default=90.0, gt=0)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    embedding_backend: EmbeddingBackendName = "auto"
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hashing_embedding_dimension: int = Field(default=512, ge=64, le=4096)
    retrieval_top_k: int = Field(default=6, ge=1, le=50)
    embedding_batch_size: int = Field(default=64, ge=1, le=512)

    # ------------------------------------------------------------------
    # Rendering / compilation
    # ------------------------------------------------------------------
    default_template: str = "treyHunner"
    latex_engine: str | None = None
    latex_timeout_seconds: float = Field(default=120.0, gt=0)

    # ------------------------------------------------------------------
    # Web service
    # ------------------------------------------------------------------
    app_name: str = "CareerX"
    environment: Literal["local", "staging", "production"] = "local"
    host: str = "0.0.0.0"  # noqa: S104 - containers must bind all interfaces
    port: int = Field(default=8000, ge=1, le=65535)
    root_path: str = ""
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    artifact_dir: Path = Path("/tmp/careerx-artifacts")  # noqa: S108
    artifact_ttl_seconds: int = Field(default=1800, ge=60, le=86_400)
    artifact_sweep_interval_seconds: int = Field(default=300, ge=30, le=3600)

    max_upload_bytes: int = Field(default=1_048_576, ge=1024)
    max_job_description_chars: int = Field(default=30_000, ge=100)

    rate_limit_requests: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------
    strict_grounding: bool = False
    """Raise instead of repairing when the model returns ungrounded content."""

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a JSON array or a comma-separated string.

        The comma form is what people actually write in a hosting provider's
        environment variable box, so both are supported.
        """
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped:
            return []

        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"CORS_ALLOW_ORIGINS is not valid JSON: {exc}") from exc

        return [item.strip() for item in stripped.split(",") if item.strip()]

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def active_api_key(self) -> str | None:
        """API key for the currently selected provider."""
        return self.google_api_key if self.llm_provider == "gemini" else self.openai_api_key

    @property
    def llm_configured(self) -> bool:
        return bool(self.active_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
