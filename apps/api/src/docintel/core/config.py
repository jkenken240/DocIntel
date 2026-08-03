from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
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
    app_version: str = "1.0.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://docintel:docintel_local_only@localhost:5432/docintel"

    uploads_path: Path = Path("/data/uploads")
    processed_path: Path = Path("/data/processed")
    samples_path: Path = Path("/data/samples")
    backups_path: Path = Path("/data/backups")

    upload_max_bytes: PositiveInt = 25 * 1024 * 1024
    upload_chunk_bytes: PositiveInt = 64 * 1024
    pdf_max_pages: PositiveInt = 500
    processing_version: str = "phase4-v1"
    processing_job_max_attempts: PositiveInt = 3
    processing_retry_base_seconds: NonNegativeInt = 2
    embedding_batch_size: PositiveInt = 32
    mock_embedding_model: str = "mock-hash-v1"
    chunk_target_chars: PositiveInt = 1400
    chunk_max_chars: PositiveInt = 1800
    chunk_overlap_chars: NonNegativeInt = 200
    chunker_version: str = "deterministic-char-v1"
    question_max_chars: PositiveInt = 2000
    question_max_documents: PositiveInt = 20
    retrieval_candidate_pool: PositiveInt = 40
    retrieval_evidence_count: PositiveInt = 6
    retrieval_minimum_similarity: float = 0.05
    retrieval_max_chunks_per_page: PositiveInt = 2
    retrieval_max_chunks_per_document: PositiveInt = 3
    retrieval_mmr_lambda: float = 0.75
    retrieval_duplicate_overlap_ratio: float = 0.7
    deletion_job_max_attempts: PositiveInt = 3
    deletion_retry_base_seconds: NonNegativeInt = 5
    worker_poll_seconds: PositiveInt = 1
    worker_lease_seconds: PositiveInt = 30

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    ai_provider: Literal["mock", "openai_compatible"] = "mock"
    embedding_dimensions: PositiveInt = 1536
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_chat_model: str | None = None
    ai_embedding_model: str | None = None
    ai_structured_output: bool = True
    ai_timeout_seconds: PositiveFloat = 20.0
    ai_max_response_bytes: PositiveInt = 64 * 1024
    mock_answer_model: str = "mock-grounded-v1"
    mock_verifier_model: str = "mock-claim-verifier-v1"

    @model_validator(mode="after")
    def validate_upload_streaming_configuration(self) -> Settings:
        if self.upload_chunk_bytes < 5:
            raise ValueError("upload_chunk_bytes must be at least 5 bytes")
        if self.upload_chunk_bytes > self.upload_max_bytes:
            raise ValueError("upload_chunk_bytes cannot exceed upload_max_bytes")
        if self.chunk_target_chars > self.chunk_max_chars:
            raise ValueError("chunk_target_chars cannot exceed chunk_max_chars")
        if self.chunk_overlap_chars >= self.chunk_target_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_target_chars")
        if self.embedding_dimensions != 1536:
            raise ValueError("The active schema requires exactly 1536 embedding dimensions")
        if not self.processing_version.strip():
            raise ValueError("processing_version is required")
        if not self.chunker_version.strip():
            raise ValueError("chunker_version is required")
        if not self.mock_embedding_model.strip():
            raise ValueError("mock_embedding_model is required")
        if not self.mock_answer_model.strip():
            raise ValueError("mock_answer_model is required")
        if not self.mock_verifier_model.strip():
            raise ValueError("mock_verifier_model is required")
        if self.question_max_chars > 4000:
            raise ValueError("question_max_chars cannot exceed the database limit")
        if self.retrieval_evidence_count > self.retrieval_candidate_pool:
            raise ValueError("retrieval_evidence_count cannot exceed retrieval_candidate_pool")
        if not -1.0 <= self.retrieval_minimum_similarity <= 1.0:
            raise ValueError("retrieval_minimum_similarity must be between -1 and 1")
        if not 0.0 <= self.retrieval_mmr_lambda <= 1.0:
            raise ValueError("retrieval_mmr_lambda must be between zero and one")
        if not 0.0 <= self.retrieval_duplicate_overlap_ratio <= 1.0:
            raise ValueError("retrieval_duplicate_overlap_ratio must be between zero and one")
        return self

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
