"""Add retrieval evidence and grounded answer audit records.

Revision ID: 20260730_0004
Revises: 20260730_0003
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260730_0004"
down_revision: str | None = "20260730_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

question_status = postgresql.ENUM(
    "processing",
    "answered",
    "insufficient_evidence",
    name="question_status",
)


def upgrade() -> None:
    question_status.create(op.get_bind(), checkfirst=True)
    op.create_unique_constraint(
        "uq_chunks_id_page_document",
        "chunks",
        ["id", "page_id", "document_id"],
    )

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column(
            "selected_document_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "processing",
                "answered",
                "insufficient_evidence",
                name="question_status",
                create_type=False,
            ),
            server_default="processing",
            nullable=False,
        ),
        sa.Column("insufficient_reason_code", sa.String(length=80), nullable=True),
        sa.Column(
            "retrieval_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("retrieval_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_space_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding_provider", sa.String(length=80), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_distance_metric", sa.String(length=32), nullable=False),
        sa.Column("embedding_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("answer_provider", sa.String(length=80), nullable=False),
        sa.Column("answer_model", sa.String(length=120), nullable=False),
        sa.Column("answer_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("verifier_provider", sa.String(length=80), nullable=False),
        sa.Column("verifier_model", sa.String(length=120), nullable=False),
        sa.Column("verifier_configuration_hash", sa.String(length=64), nullable=False),
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
        sa.CheckConstraint(
            "char_length(normalized_text) BETWEEN 1 AND 4000",
            name="ck_questions_normalized_text_length",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_space_id"],
            ["embedding_spaces.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_created_at", "questions", ["created_at"])

    op.create_table(
        "evidence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_filename", sa.String(length=255), nullable=False),
        sa.Column("processing_revision", sa.Integer(), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("embedding_space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_provider", sa.String(length=80), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_distance_metric", sa.String(length=32), nullable=False),
        sa.Column("embedding_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_revision > 0",
            name="ck_evidence_processing_revision",
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_evidence_page_number"),
        sa.CheckConstraint("chunk_ordinal >= 0", name="ck_evidence_chunk_ordinal"),
        sa.CheckConstraint("char_start >= 0", name="ck_evidence_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_evidence_char_range"),
        sa.CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_evidence_text_length",
        ),
        sa.CheckConstraint("retrieval_rank >= 1", name="ck_evidence_retrieval_rank"),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "page_id", "document_id"],
            ["chunks.id", "chunks.page_id", "chunks.document_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_space_id"],
            ["embedding_spaces.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id",
            "retrieval_rank",
            name="uq_evidence_question_rank",
        ),
        sa.UniqueConstraint(
            "question_id",
            "chunk_id",
            name="uq_evidence_question_chunk",
        ),
    )
    op.create_index(
        "ix_evidence_document_id",
        "evidence_snapshots",
        ["document_id"],
    )
    op.create_index(
        "ix_evidence_question_id",
        "evidence_snapshots",
        ["question_id"],
    )

    op.create_table(
        "answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(text) > 0", name="ck_answers_text_nonempty"),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", name="uq_answers_question"),
    )

    op.create_table(
        "answer_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_answer_claims_ordinal"),
        sa.CheckConstraint("char_start >= 0", name="ck_answer_claims_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_answer_claims_char_range"),
        sa.CheckConstraint(
            "char_length(text) = char_end - char_start",
            name="ck_answer_claims_text_length",
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "answer_id",
            "ordinal",
            name="uq_answer_claims_answer_ordinal",
        ),
    )

    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_citations_ordinal"),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["answer_claims.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["evidence_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "claim_id",
            "ordinal",
            name="uq_citations_claim_ordinal",
        ),
        sa.UniqueConstraint(
            "claim_id",
            "evidence_snapshot_id",
            name="uq_citations_claim_evidence",
        ),
    )

    op.create_table(
        "claim_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["answer_claims.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", name="uq_claim_verifications_claim"),
    )

    op.create_table(
        "claim_verification_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_verification_evidence_ordinal",
        ),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["claim_verifications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["evidence_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "verification_id",
            "ordinal",
            name="uq_verification_evidence_ordinal",
        ),
        sa.UniqueConstraint(
            "verification_id",
            "evidence_snapshot_id",
            name="uq_verification_evidence_snapshot",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION docintel_reject_evidence_snapshot_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'evidence snapshots are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_evidence_snapshots_immutable
        BEFORE UPDATE ON evidence_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION docintel_reject_evidence_snapshot_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION docintel_delete_dependent_questions()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            DELETE FROM questions
            WHERE id IN (
                SELECT question_id
                FROM evidence_snapshots
                WHERE document_id = OLD.id
            );
            RETURN OLD;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_documents_delete_dependent_questions
        BEFORE DELETE ON documents
        FOR EACH ROW
        EXECUTE FUNCTION docintel_delete_dependent_questions()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_documents_delete_dependent_questions ON documents")
    op.execute("DROP FUNCTION IF EXISTS docintel_delete_dependent_questions()")
    op.execute("DROP TRIGGER IF EXISTS tr_evidence_snapshots_immutable ON evidence_snapshots")
    op.execute("DROP FUNCTION IF EXISTS docintel_reject_evidence_snapshot_update()")

    op.drop_table("claim_verification_evidence")
    op.drop_table("claim_verifications")
    op.drop_table("citations")
    op.drop_table("answer_claims")
    op.drop_table("answers")
    op.drop_index("ix_evidence_question_id", table_name="evidence_snapshots")
    op.drop_index("ix_evidence_document_id", table_name="evidence_snapshots")
    op.drop_table("evidence_snapshots")
    op.drop_index("ix_questions_created_at", table_name="questions")
    op.drop_table("questions")
    op.drop_constraint("uq_chunks_id_page_document", "chunks", type_="unique")
    question_status.drop(op.get_bind(), checkfirst=True)
