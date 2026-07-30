from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docintel.db.base import Base
from docintel.models.document import DocumentStage, ProgressUnit, enum_values

if TYPE_CHECKING:
    from docintel.models.document import Document


class JobKind(StrEnum):
    PROCESSING = "processing"
    DELETION = "deletion"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DocumentJob(Base):
    __tablename__ = "document_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_document_jobs_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_document_jobs_max_attempts"),
        CheckConstraint("progress_completed >= 0", name="ck_document_jobs_progress_completed"),
        CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_document_jobs_progress_total",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_completed <= progress_total",
            name="ck_document_jobs_progress_within_total",
        ),
        CheckConstraint(
            "processing_revision > 0",
            name="ck_document_jobs_processing_revision_positive",
        ),
        Index(
            "uq_document_jobs_active_kind",
            "document_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_document_jobs_claim", "kind", "status", "available_at"),
        Index("ix_document_jobs_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[JobKind] = mapped_column(
        Enum(JobKind, name="job_kind", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=enum_values),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
    )
    attempts: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3, server_default="3")
    processing_revision: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        server_default="1",
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
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
    stage: Mapped[DocumentStage | None] = mapped_column(
        Enum(
            DocumentStage,
            name="document_stage",
            values_callable=enum_values,
        )
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    failure_retryable: Mapped[bool | None] = mapped_column(Boolean)
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
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="jobs")
