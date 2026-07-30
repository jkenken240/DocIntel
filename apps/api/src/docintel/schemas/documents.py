from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from docintel.models import Document, DocumentStage, DocumentStatus, ProgressUnit


class DocumentProgress(BaseModel):
    completed: int = Field(ge=0)
    total: int | None = Field(default=None, ge=0)
    unit: ProgressUnit | None = None


class DocumentError(BaseModel):
    code: str
    message: str
    retryable: bool | None = None


class DocumentSummary(BaseModel):
    id: uuid.UUID
    name: str
    media_type: str
    byte_size: int
    status: DocumentStatus
    stage: DocumentStage
    progress: DocumentProgress
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, document: Document) -> DocumentSummary:
        return cls(
            id=document.id,
            name=document.original_filename,
            media_type=document.media_type,
            byte_size=document.byte_size,
            status=document.status,
            stage=document.stage,
            progress=DocumentProgress(
                completed=document.progress_completed,
                total=document.progress_total,
                unit=document.progress_unit,
            ),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class DocumentDetail(DocumentSummary):
    sha256: str
    page_count: int
    text_page_count: int
    chunk_count: int
    processing_revision: int
    processing_version: str
    pdf_metadata: dict[str, str]
    stage_started_at: datetime | None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    error: DocumentError | None = None

    @classmethod
    def from_document(cls, document: Document) -> DocumentDetail:
        summary = DocumentSummary.from_document(document)
        error = (
            DocumentError(
                code=document.error_code,
                message=document.error_message,
                retryable=document.error_retryable,
            )
            if document.error_code and document.error_message
            else None
        )
        return cls(
            **summary.model_dump(),
            sha256=document.sha256,
            page_count=document.page_count,
            text_page_count=document.text_page_count,
            chunk_count=document.chunk_count,
            processing_revision=document.processing_revision,
            processing_version=document.processing_version,
            pdf_metadata=document.pdf_metadata,
            stage_started_at=document.stage_started_at,
            processing_started_at=document.processing_started_at,
            processing_completed_at=document.processing_completed_at,
            error=error,
        )


class DocumentStatusResponse(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    stage: DocumentStage
    progress: DocumentProgress
    error: DocumentError | None = None
    updated_at: datetime

    @classmethod
    def from_document(cls, document: Document) -> DocumentStatusResponse:
        detail = DocumentDetail.from_document(document)
        return cls(
            id=detail.id,
            status=detail.status,
            stage=detail.stage,
            progress=detail.progress,
            error=detail.error,
            updated_at=detail.updated_at,
        )


class DocumentEnvelope(BaseModel):
    document: DocumentDetail


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    next_cursor: str | None = None


DocumentSort = Literal["created_at", "name", "size"]
SortOrder = Literal["asc", "desc"]


class DocumentCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    sort: DocumentSort
    order: SortOrder
    value: str | int
    id: uuid.UUID
