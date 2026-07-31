"""add evidence_findings table

Revision ID: 012bbc9b0b87
Revises: 73fa8c732b45
Create Date: 2026-07-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012bbc9b0b87"
down_revision: Union[str, Sequence[str], None] = "73fa8c732b45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "evidence_findings",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=True),
        sa.Column("agent", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("relevance", sa.String(length=10), nullable=False),
        sa.Column("suggested_use", sa.Text(), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="DRAFT_PENDING_REVIEW",
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
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_findings_tenant_id"), "evidence_findings", ["tenant_id"])
    op.create_index(op.f("ix_evidence_findings_case_id"), "evidence_findings", ["case_id"])
    op.create_index(op.f("ix_evidence_findings_evidence_id"), "evidence_findings", ["evidence_id"])

    # --- Row Level Security (mesmo padrão das migrations anteriores) ---
    op.execute("ALTER TABLE evidence_findings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_findings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON evidence_findings "
        f"USING (tenant_id = {_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (tenant_id = {_TENANT_ISOLATION_EXPR})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON evidence_findings")
    op.execute("ALTER TABLE evidence_findings NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_findings DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_evidence_findings_evidence_id"), table_name="evidence_findings")
    op.drop_index(op.f("ix_evidence_findings_case_id"), table_name="evidence_findings")
    op.drop_index(op.f("ix_evidence_findings_tenant_id"), table_name="evidence_findings")
    op.drop_table("evidence_findings")
