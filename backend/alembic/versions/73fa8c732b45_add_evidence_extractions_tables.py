"""add evidence_extractions and evidence_extraction_reviews tables

Revision ID: 73fa8c732b45
Revises: f39dd1e27be8
Create Date: 2026-07-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73fa8c732b45"
down_revision: Union[str, Sequence[str], None] = "f39dd1e27be8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (tenant_id = {_TENANT_ISOLATION_EXPR})"
    )


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    """Upgrade schema."""
    # Tipos criados explicitamente e referenciados com create_type=False nas
    # colunas (mesmo padrão da migration 41280d8b096c).
    extraction_outcome = postgresql.ENUM("succeeded", "failed", name="extraction_outcome")
    extraction_outcome.create(op.get_bind(), checkfirst=True)
    extraction_outcome_col = postgresql.ENUM(
        "succeeded", "failed", name="extraction_outcome", create_type=False
    )
    review_verdict = postgresql.ENUM(
        "confirmed", "extraction_error", name="extraction_review_verdict"
    )
    review_verdict.create(op.get_bind(), checkfirst=True)
    review_verdict_col = postgresql.ENUM(
        "confirmed", "extraction_error", name="extraction_review_verdict", create_type=False
    )

    op.create_table(
        "evidence_extractions",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("outcome", extraction_outcome_col, nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("tool_version", sa.String(length=50), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
    op.create_index(
        op.f("ix_evidence_extractions_tenant_id"), "evidence_extractions", ["tenant_id"]
    )
    op.create_index(op.f("ix_evidence_extractions_case_id"), "evidence_extractions", ["case_id"])
    op.create_index(
        op.f("ix_evidence_extractions_evidence_id"), "evidence_extractions", ["evidence_id"]
    )
    _enable_rls("evidence_extractions")

    op.create_table(
        "evidence_extraction_reviews",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("extraction_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), nullable=False),
        sa.Column("verdict", review_verdict_col, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["evidence_extractions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_extraction_reviews_tenant_id"),
        "evidence_extraction_reviews",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_evidence_extraction_reviews_case_id"), "evidence_extraction_reviews", ["case_id"]
    )
    op.create_index(
        op.f("ix_evidence_extraction_reviews_extraction_id"),
        "evidence_extraction_reviews",
        ["extraction_id"],
    )
    _enable_rls("evidence_extraction_reviews")


def downgrade() -> None:
    """Downgrade schema."""
    _disable_rls("evidence_extraction_reviews")
    op.drop_index(
        op.f("ix_evidence_extraction_reviews_extraction_id"),
        table_name="evidence_extraction_reviews",
    )
    op.drop_index(
        op.f("ix_evidence_extraction_reviews_case_id"), table_name="evidence_extraction_reviews"
    )
    op.drop_index(
        op.f("ix_evidence_extraction_reviews_tenant_id"), table_name="evidence_extraction_reviews"
    )
    op.drop_table("evidence_extraction_reviews")

    _disable_rls("evidence_extractions")
    op.drop_index(
        op.f("ix_evidence_extractions_evidence_id"), table_name="evidence_extractions"
    )
    op.drop_index(op.f("ix_evidence_extractions_case_id"), table_name="evidence_extractions")
    op.drop_index(op.f("ix_evidence_extractions_tenant_id"), table_name="evidence_extractions")
    op.drop_table("evidence_extractions")

    postgresql.ENUM(name="extraction_review_verdict").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="extraction_outcome").drop(op.get_bind(), checkfirst=True)
