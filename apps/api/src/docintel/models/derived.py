from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docintel.db.base import Base

if TYPE_CHECKING:
    from docintel.models.document import Document
    from docintel.models.embedding import ChunkEmbedding


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        CheckConstraint("processing_revision > 0", name="ck_document_pages_revision"),
        CheckConstraint("page_number >= 1", name="ck_document_pages_page_number"),
        CheckConstraint("width > 0", name="ck_document_pages_width"),
        CheckConstraint("height > 0", name="ck_document_pages_height"),
        CheckConstraint("char_count >= 0", name="ck_document_pages_char_count"),
        CheckConstraint(
            "char_count = char_length(text)",
            name="ck_document_pages_text_length",
        ),
        UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_pages_document_page",
        ),
        UniqueConstraint(
            "id",
            "document_id",
            name="uq_document_pages_id_document",
        ),
        Index("ix_document_pages_document_id", "document_id"),
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
    processing_revision: Mapped[int] = mapped_column(nullable=False)
    page_number: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(back_populates="pages")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("processing_revision > 0", name="ck_chunks_revision"),
        CheckConstraint("ordinal >= 0", name="ck_chunks_ordinal"),
        CheckConstraint("page_ordinal >= 0", name="ck_chunks_page_ordinal"),
        CheckConstraint("char_start >= 0", name="ck_chunks_char_start"),
        CheckConstraint("char_end > char_start", name="ck_chunks_char_range"),
        CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_chunks_text_length",
        ),
        ForeignKeyConstraint(
            ["page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_chunks_document_ordinal",
        ),
        UniqueConstraint(
            "page_id",
            "page_ordinal",
            name="uq_chunks_page_ordinal",
        ),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_page_id", "page_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_revision: Mapped[int] = mapped_column(nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    page_ordinal: Mapped[int] = mapped_column(nullable=False)
    char_start: Mapped[int] = mapped_column(nullable=False)
    char_end: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    page: Mapped[DocumentPage] = relationship(back_populates="chunks")
    embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
