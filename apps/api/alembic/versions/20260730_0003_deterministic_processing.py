"""Add deterministic document processing and embeddings.

Revision ID: 20260730_0003
Revises: 20260730_0002
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260730_0003"
down_revision: str | None = "20260730_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_stage = postgresql.ENUM(
    "queued",
    "validating",
    "extracting",
    "chunking",
    "embedding",
    "deleting",
    name="document_stage",
    create_type=False,
)
progress_unit = postgresql.ENUM(
    "bytes",
    "pages",
    "chunks",
    name="progress_unit",
    create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processing_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column(
            "processing_version",
            sa.String(length=80),
            server_default="phase4-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("text_page_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column(
            "pdf_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("documents", sa.Column("error_retryable", sa.Boolean(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("stage_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_documents_processing_revision_positive",
        "documents",
        "processing_revision > 0",
    )
    op.create_check_constraint(
        "ck_documents_text_page_count",
        "documents",
        "text_page_count >= 0",
    )
    op.create_check_constraint(
        "ck_documents_text_page_count_within_total",
        "documents",
        "text_page_count <= page_count",
    )
    op.create_check_constraint(
        "ck_documents_progress_within_total",
        "documents",
        "progress_total IS NULL OR progress_completed <= progress_total",
    )

    op.add_column(
        "document_jobs",
        sa.Column("processing_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "document_jobs",
        sa.Column("stage", document_stage, nullable=True),
    )
    op.add_column(
        "document_jobs",
        sa.Column("progress_unit", progress_unit, nullable=True),
    )
    op.add_column(
        "document_jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_jobs",
        sa.Column("stage_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_jobs",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_jobs",
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
    )
    op.create_check_constraint(
        "ck_document_jobs_processing_revision_positive",
        "document_jobs",
        "processing_revision > 0",
    )
    op.create_check_constraint(
        "ck_document_jobs_progress_within_total",
        "document_jobs",
        "progress_total IS NULL OR progress_completed <= progress_total",
    )

    op.create_table(
        "embedding_spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(length=32), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("dimensions = 1536", name="ck_embedding_spaces_dimensions"),
        sa.CheckConstraint(
            "distance_metric = 'cosine'",
            name="ck_embedding_spaces_distance_metric",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "model",
            "dimensions",
            "distance_metric",
            "configuration_hash",
            name="uq_embedding_spaces_identity",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "active_embedding_space_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_documents_active_embedding_space_id",
        "documents",
        "embedding_spaces",
        ["active_embedding_space_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_documents_active_embedding_space_id",
        "documents",
        ["active_embedding_space_id"],
    )

    op.create_table(
        "document_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_revision", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("processing_revision > 0", name="ck_document_pages_revision"),
        sa.CheckConstraint("page_number >= 1", name="ck_document_pages_page_number"),
        sa.CheckConstraint("width > 0", name="ck_document_pages_width"),
        sa.CheckConstraint("height > 0", name="ck_document_pages_height"),
        sa.CheckConstraint("char_count >= 0", name="ck_document_pages_char_count"),
        sa.CheckConstraint(
            "char_count = char_length(text)",
            name="ck_document_pages_text_length",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_pages_document_page",
        ),
        sa.UniqueConstraint(
            "id",
            "document_id",
            name="uq_document_pages_id_document",
        ),
    )
    op.create_index(
        "ix_document_pages_document_id",
        "document_pages",
        ["document_id"],
    )

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_revision", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("processing_revision > 0", name="ck_chunks_revision"),
        sa.CheckConstraint("ordinal >= 0", name="ck_chunks_ordinal"),
        sa.CheckConstraint("page_ordinal >= 0", name="ck_chunks_page_ordinal"),
        sa.CheckConstraint("char_start >= 0", name="ck_chunks_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_chunks_char_range"),
        sa.CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_chunks_text_length",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_chunks_document_ordinal",
        ),
        sa.UniqueConstraint(
            "page_id",
            "page_ordinal",
            name="uq_chunks_page_ordinal",
        ),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_page_id", "chunks", ["page_id"])

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "embedding_space_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["embedding_space_id"],
            ["embedding_spaces.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id",
            "embedding_space_id",
            name="uq_chunk_embeddings_chunk_space",
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_embedding_space_id",
        "chunk_embeddings",
        ["embedding_space_id"],
    )
    op.create_index(
        "ix_chunk_embeddings_vector_cosine",
        "chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_embeddings_vector_cosine", table_name="chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_embedding_space_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.drop_index("ix_chunks_page_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")

    op.drop_index("ix_documents_active_embedding_space_id", table_name="documents")
    op.drop_constraint(
        "fk_documents_active_embedding_space_id",
        "documents",
        type_="foreignkey",
    )
    op.drop_column("documents", "active_embedding_space_id")
    op.drop_table("embedding_spaces")

    op.drop_constraint(
        "ck_document_jobs_progress_within_total",
        "document_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_document_jobs_processing_revision_positive",
        "document_jobs",
        type_="check",
    )
    op.drop_column("document_jobs", "failure_retryable")
    op.drop_column("document_jobs", "last_heartbeat_at")
    op.drop_column("document_jobs", "stage_started_at")
    op.drop_column("document_jobs", "started_at")
    op.drop_column("document_jobs", "progress_unit")
    op.drop_column("document_jobs", "stage")
    op.drop_column("document_jobs", "processing_revision")

    op.drop_constraint(
        "ck_documents_progress_within_total",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_text_page_count_within_total",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_text_page_count",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_processing_revision_positive",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "processing_completed_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "stage_started_at")
    op.drop_column("documents", "error_retryable")
    op.drop_column("documents", "pdf_metadata")
    op.drop_column("documents", "text_page_count")
    op.drop_column("documents", "processing_version")
    op.drop_column("documents", "processing_revision")
