from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docintel.db.base import Base

if TYPE_CHECKING:
    from docintel.models.derived import Chunk
    from docintel.models.document import Document


class EmbeddingSpace(Base):
    __tablename__ = "embedding_spaces"
    __table_args__ = (
        CheckConstraint("dimensions = 1536", name="ck_embedding_spaces_dimensions"),
        CheckConstraint(
            "distance_metric = 'cosine'",
            name="ck_embedding_spaces_distance_metric",
        ),
        UniqueConstraint(
            "provider",
            "model",
            "dimensions",
            "distance_metric",
            "configuration_hash",
            name="uq_embedding_spaces_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    documents: Mapped[list[Document]] = relationship(back_populates="active_embedding_space")
    chunk_embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        back_populates="embedding_space",
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "embedding_space_id",
            name="uq_chunk_embeddings_chunk_space",
        ),
        Index("ix_chunk_embeddings_embedding_space_id", "embedding_space_id"),
        Index(
            "ix_chunk_embeddings_vector_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_spaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chunk: Mapped[Chunk] = relationship(back_populates="embeddings")
    embedding_space: Mapped[EmbeddingSpace] = relationship(back_populates="chunk_embeddings")
