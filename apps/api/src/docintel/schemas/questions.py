from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from docintel.models import QuestionStatus


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class ProviderSnapshot(BaseModel):
    provider: str
    model: str
    configuration_hash: str


class EmbeddingSpaceSnapshot(ProviderSnapshot):
    id: uuid.UUID | None
    dimensions: int
    distance_metric: str


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    processing_revision: int
    page_id: uuid.UUID
    page_number: int
    chunk_id: uuid.UUID
    chunk_ordinal: int
    char_start: int
    char_end: int
    excerpt: str
    text_sha256: str
    retrieval_score: float
    retrieval_rank: int


class CitationResponse(BaseModel):
    id: uuid.UUID
    evidence_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_id: uuid.UUID
    char_start: int
    char_end: int
    excerpt: str
    text_sha256: str
    retrieval_score: float
    retrieval_rank: int


class ClaimResponse(BaseModel):
    id: uuid.UUID
    ordinal: int
    char_start: int
    char_end: int
    text: str
    supported: bool
    verification_reason_code: str
    citations: list[CitationResponse]


class QuestionResponse(BaseModel):
    id: uuid.UUID
    question: str
    selected_document_ids: list[uuid.UUID]
    status: QuestionStatus
    insufficient_reason_code: str | None
    answer_id: uuid.UUID | None
    answer_text: str | None
    claims: list[ClaimResponse]
    evidence: list[EvidenceResponse]
    retrieval_configuration: dict[str, int | float]
    retrieval_configuration_hash: str
    embedding_space: EmbeddingSpaceSnapshot
    answer_provider: ProviderSnapshot
    verifier_provider: ProviderSnapshot
    created_at: datetime
