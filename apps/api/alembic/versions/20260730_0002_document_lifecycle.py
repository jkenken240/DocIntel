"""Add secure document lifecycle tables.

Revision ID: 20260730_0002
Revises: 20260730_0001
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260730_0002"
down_revision: str | None = "20260730_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_status = postgresql.ENUM(
    "queued",
    "processing",
    "ready",
    "failed",
    "deleting",
    name="document_status",
    create_type=False,
)
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
job_kind = postgresql.ENUM(
    "processing",
    "deletion",
    name="job_kind",
    create_type=False,
)
job_status = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="job_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    document_status.create(bind, checkfirst=True)
    document_stage.create(bind, checkfirst=True)
    progress_unit.create(bind, checkfirst=True)
    job_kind.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=128), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", document_status, server_default="queued", nullable=False),
        sa.Column("stage", document_stage, server_default="queued", nullable=False),
        sa.Column("progress_completed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column("progress_unit", progress_unit, nullable=True),
        sa.Column("page_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deletion_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_documents_byte_size_positive"),
        sa.CheckConstraint(
            "progress_completed >= 0",
            name="ck_documents_progress_completed",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_documents_progress_total",
        ),
        sa.CheckConstraint("page_count >= 0", name="ck_documents_page_count"),
        sa.CheckConstraint("chunk_count >= 0", name="ck_documents_chunk_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_documents_created_at", "documents", ["created_at"])
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", "created_at"],
    )

    op.create_table(
        "document_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", job_kind, nullable=False),
        sa.Column("status", job_status, server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("progress_completed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_document_jobs_attempts"),
        sa.CheckConstraint("max_attempts > 0", name="ck_document_jobs_max_attempts"),
        sa.CheckConstraint(
            "progress_completed >= 0",
            name="ck_document_jobs_progress_completed",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_document_jobs_progress_total",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_jobs_claim",
        "document_jobs",
        ["kind", "status", "available_at"],
    )
    op.create_index("ix_document_jobs_document_id", "document_jobs", ["document_id"])
    op.create_index(
        "uq_document_jobs_active_kind",
        "document_jobs",
        ["document_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_document_jobs_active_kind", table_name="document_jobs")
    op.drop_index("ix_document_jobs_document_id", table_name="document_jobs")
    op.drop_index("ix_document_jobs_claim", table_name="document_jobs")
    op.drop_table("document_jobs")
    op.drop_index("ix_documents_status_created_at", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_table("documents")

    bind = op.get_bind()
    job_status.drop(bind, checkfirst=True)
    job_kind.drop(bind, checkfirst=True)
    progress_unit.drop(bind, checkfirst=True)
    document_stage.drop(bind, checkfirst=True)
    document_status.drop(bind, checkfirst=True)
