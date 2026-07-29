from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docintel.db.base import Base

if TYPE_CHECKING:
    from docintel.models.job import DocumentJob


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class DocumentStage(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    DELETING = "deleting"


class ProgressUnit(StrEnum):
    BYTES = "bytes"
    PAGES = "pages"
    CHUNKS = "chunks"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_documents_byte_size_positive"),
        CheckConstraint("progress_completed >= 0", name="ck_documents_progress_completed"),
        CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_documents_progress_total",
        ),
        CheckConstraint("page_count >= 0", name="ck_documents_page_count"),
        CheckConstraint("chunk_count >= 0", name="ck_documents_chunk_count"),
        Index("ix_documents_status_created_at", "status", "created_at"),
        Index("ix_documents_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=DocumentStatus.QUEUED,
        server_default=DocumentStatus.QUEUED.value,
    )
    stage: Mapped[DocumentStage] = mapped_column(
        Enum(
            DocumentStage,
            name="document_stage",
            values_callable=enum_values,
        ),
        nullable=False,
        default=DocumentStage.QUEUED,
        server_default=DocumentStage.QUEUED.value,
    )
    progress_completed: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    progress_total: Mapped[int | None] = mapped_column(BigInteger)
    progress_unit: Mapped[ProgressUnit | None] = mapped_column(
        Enum(
            ProgressUnit,
            name="progress_unit",
            values_callable=enum_values,
        )
    )
    page_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    chunk_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    deletion_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    jobs: Mapped[list[DocumentJob]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
