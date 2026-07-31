"""add evidence_files table

Revision ID: f39dd1e27be8
Revises: 48c0ad76f3dd
Create Date: 2026-07-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f39dd1e27be8"
down_revision: Union[str, Sequence[str], None] = "48c0ad76f3dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    """Upgrade schema."""
    # Cria o tipo explicitamente e referencia com create_type=False na coluna
    # (mesmo padrão de document_checklist_status na migration 41280d8b096c:
    # op.create_table dispara seu próprio CREATE TYPE para enums com
    # create_type=True, duplicando o comando).
    evidence_processing_status = postgresql.ENUM(
        "received", "processing", "processed", "failed", name="evidence_processing_status"
    )
    evidence_processing_status.create(op.get_bind(), checkfirst=True)
    evidence_processing_status_col = postgresql.ENUM(
        "received",
        "processing",
        "processed",
        "failed",
        name="evidence_processing_status",
        create_type=False,
    )

    op.create_table(
        "evidence_files",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("extension", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("origin", sa.String(length=50), server_default="upload_portal", nullable=False),
        sa.Column(
            "status", evidence_processing_status_col, server_default="received", nullable=False
        ),
        sa.Column("duplicate_of_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["evidence_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_evidence_files_storage_key"),
    )
    op.create_index(
        op.f("ix_evidence_files_tenant_id"), "evidence_files", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_evidence_files_case_id"), "evidence_files", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_evidence_files_uploaded_by"), "evidence_files", ["uploaded_by"], unique=False
    )
    op.create_index(
        op.f("ix_evidence_files_sha256_hash"), "evidence_files", ["sha256_hash"], unique=False
    )

    # --- Row Level Security (mesmo padrão de 0406e102877a/3abdfd696724) ---
    op.execute("ALTER TABLE evidence_files ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_files FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON evidence_files "
        f"USING (tenant_id = {_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (tenant_id = {_TENANT_ISOLATION_EXPR})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON evidence_files")
    op.execute("ALTER TABLE evidence_files NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_files DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_evidence_files_sha256_hash"), table_name="evidence_files")
    op.drop_index(op.f("ix_evidence_files_uploaded_by"), table_name="evidence_files")
    op.drop_index(op.f("ix_evidence_files_case_id"), table_name="evidence_files")
    op.drop_index(op.f("ix_evidence_files_tenant_id"), table_name="evidence_files")
    op.drop_table("evidence_files")

    postgresql.ENUM(name="evidence_processing_status").drop(op.get_bind(), checkfirst=True)
