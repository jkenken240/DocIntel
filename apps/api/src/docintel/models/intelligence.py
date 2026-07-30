from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docintel.db.base import Base
from docintel.models.document import enum_values

if TYPE_CHECKING:
    from docintel.models.derived import Chunk, DocumentPage
    from docintel.models.document import Document
    from docintel.models.embedding import EmbeddingSpace


class QuestionStatus(StrEnum):
    PROCESSING = "processing"
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "char_length(normalized_text) BETWEEN 1 AND 4000",
            name="ck_questions_normalized_text_length",
        ),
        Index("ix_questions_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    selected_document_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus, name="question_status", values_callable=enum_values),
        nullable=False,
        default=QuestionStatus.PROCESSING,
        server_default=QuestionStatus.PROCESSING.value,
    )
    insufficient_reason_code: Mapped[str | None] = mapped_column(String(80))
    retrieval_configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    retrieval_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_spaces.id", ondelete="RESTRICT"),
    )
    embedding_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding_distance_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answer_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    answer_model: Mapped[str] = mapped_column(String(120), nullable=False)
    answer_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    verifier_model: Mapped[str] = mapped_column(String(120), nullable=False)
    verifier_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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

    embedding_space: Mapped[EmbeddingSpace | None] = relationship()
    evidence: Mapped[list[EvidenceSnapshot]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvidenceSnapshot.retrieval_rank",
    )
    answer: Mapped[Answer | None] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = (
        CheckConstraint("processing_revision > 0", name="ck_evidence_processing_revision"),
        CheckConstraint("page_number >= 1", name="ck_evidence_page_number"),
        CheckConstraint("chunk_ordinal >= 0", name="ck_evidence_chunk_ordinal"),
        CheckConstraint("char_start >= 0", name="ck_evidence_char_start"),
        CheckConstraint("char_end > char_start", name="ck_evidence_char_range"),
        CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_evidence_text_length",
        ),
        CheckConstraint("retrieval_rank >= 1", name="ck_evidence_retrieval_rank"),
        ForeignKeyConstraint(
            ["page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["chunk_id", "page_id", "document_id"],
            ["chunks.id", "chunks.page_id", "chunks.document_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("question_id", "retrieval_rank", name="uq_evidence_question_rank"),
        UniqueConstraint("question_id", "chunk_id", name="uq_evidence_question_chunk"),
        Index("ix_evidence_document_id", "document_id"),
        Index("ix_evidence_question_id", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_revision: Mapped[int] = mapped_column(nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_number: Mapped[int] = mapped_column(nullable=False)
    page_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_ordinal: Mapped[int] = mapped_column(nullable=False)
    char_start: Mapped[int] = mapped_column(nullable=False)
    char_end: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_score: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_rank: Mapped[int] = mapped_column(nullable=False)
    embedding_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_spaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedding_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding_distance_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    question: Mapped[Question] = relationship(back_populates="evidence")
    document: Mapped[Document] = relationship(viewonly=True)
    page: Mapped[DocumentPage] = relationship(viewonly=True)
    chunk: Mapped[Chunk] = relationship(viewonly=True)
    embedding_space: Mapped[EmbeddingSpace] = relationship(viewonly=True)
    citations: Mapped[list[Citation]] = relationship(
        back_populates="evidence",
        passive_deletes=True,
    )
    verification_links: Mapped[list[ClaimVerificationEvidence]] = relationship(
        back_populates="evidence",
        passive_deletes=True,
    )


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        CheckConstraint("char_length(text) > 0", name="ck_answers_text_nonempty"),
        UniqueConstraint("question_id", name="uq_answers_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    question: Mapped[Question] = relationship(back_populates="answer")
    claims: Mapped[list[AnswerClaim]] = relationship(
        back_populates="answer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnswerClaim.ordinal",
    )


class AnswerClaim(Base):
    __tablename__ = "answer_claims"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_answer_claims_ordinal"),
        CheckConstraint("char_start >= 0", name="ck_answer_claims_char_start"),
        CheckConstraint("char_end > char_start", name="ck_answer_claims_char_range"),
        CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_answer_claims_text_length",
        ),
        UniqueConstraint("answer_id", "ordinal", name="uq_answer_claims_answer_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)
    char_start: Mapped[int] = mapped_column(nullable=False)
    char_end: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    answer: Mapped[Answer] = relationship(back_populates="claims")
    citations: Mapped[list[Citation]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Citation.ordinal",
    )
    verification: Mapped[ClaimVerification | None] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class Citation(Base):
    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_citations_ordinal"),
        UniqueConstraint("claim_id", "ordinal", name="uq_citations_claim_ordinal"),
        UniqueConstraint("claim_id", "evidence_snapshot_id", name="uq_citations_claim_evidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer_claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    claim: Mapped[AnswerClaim] = relationship(back_populates="citations")
    evidence: Mapped[EvidenceSnapshot] = relationship(back_populates="citations")


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"
    __table_args__ = (UniqueConstraint("claim_id", name="uq_claim_verifications_claim"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer_claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    claim: Mapped[AnswerClaim] = relationship(back_populates="verification")
    evidence_links: Mapped[list[ClaimVerificationEvidence]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClaimVerificationEvidence.ordinal",
    )


class ClaimVerificationEvidence(Base):
    __tablename__ = "claim_verification_evidence"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_verification_evidence_ordinal"),
        UniqueConstraint(
            "verification_id",
            "ordinal",
            name="uq_verification_evidence_ordinal",
        ),
        UniqueConstraint(
            "verification_id",
            "evidence_snapshot_id",
            name="uq_verification_evidence_snapshot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)

    verification: Mapped[ClaimVerification] = relationship(back_populates="evidence_links")
    evidence: Mapped[EvidenceSnapshot] = relationship(back_populates="verification_links")
