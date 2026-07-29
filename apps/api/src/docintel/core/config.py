from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DOCINTEL_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "DocIntel API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://docintel:docintel_local_only@localhost:5432/docintel"

    uploads_path: Path = Path("/data/uploads")
    processed_path: Path = Path("/data/processed")
    samples_path: Path = Path("/data/samples")
    backups_path: Path = Path("/data/backups")

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    ai_provider: Literal["mock", "openai_compatible"] = "mock"
    embedding_dimensions: PositiveInt = 1536
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_chat_model: str | None = None
    ai_embedding_model: str | None = None
    ai_structured_output: bool = True

    @property
    def storage_paths(self) -> dict[str, tuple[Path, bool]]:
        """Return storage paths with whether write access is required."""

        return {
            "uploads": (self.uploads_path, True),
            "processed": (self.processed_path, True),
            "samples": (self.samples_path, False),
            "backups": (self.backups_path, True),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
