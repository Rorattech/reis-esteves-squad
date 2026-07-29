"""add clients case_intakes case_documents and case classification fields

Revision ID: 41280d8b096c
Revises: d27cf82e3178
Create Date: 2026-07-29 13:48:04.814110

Camada de domínio da Fase 2 — Intake e Roteamento (ver
docs/roadmap_mvp_squad_digital.md, seção 2.1):

- clients: cliente (parte lesada) vinculado ao tenant.
- cases: ganha client_id, area, matter (classificação da triagem),
  current_module (etapa do fluxo LangGraph) e human_review_required.
- case_intakes: relato inicial estruturado (1:1 com cases).
- case_documents: checklist de documentos (recebido/pendente/dispensado).
- audit_logs.case_id passa a aceitar NULL: cadastro de cliente é auditável
  antes de qualquer caso existir (ver app/core/audit.py).

Todas as tabelas novas seguem o mesmo padrão de RLS das migrations
anteriores (0406e102877a, 3abdfd696724, e5c113039c58): tenant_id NOT NULL +
ENABLE/FORCE ROW LEVEL SECURITY + policy tenant_isolation com a expressão
"endurecida" contra app.current_tenant = ''.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41280d8b096c"
down_revision: Union[str, Sequence[str], None] = "d27cf82e3178"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_RLS_TABLES = ("clients", "case_intakes", "case_documents")


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (tenant_id = {_TENANT_ISOLATION_EXPR})"
    )


def _disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    """Upgrade schema."""
    # --- clients ---
    op.create_table(
        "clients",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("document_number", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "document_number", name="uq_clients_tenant_id_document_number"
        ),
    )
    op.create_index(op.f("ix_clients_tenant_id"), "clients", ["tenant_id"], unique=False)

    # --- cases: classificação da triagem + vínculo com cliente ---
    case_area = postgresql.ENUM(
        "civil", "family", "criminal", "labor", "consumer", "digital", name="case_area"
    )
    case_area.create(op.get_bind(), checkfirst=True)
    module_name = postgresql.ENUM(
        "intake",
        "evidence",
        "research",
        "strategy",
        "drafting",
        "review",
        name="module_name",
        create_type=False,
    )

    op.add_column("cases", sa.Column("client_id", sa.UUID(), nullable=True))
    op.add_column("cases", sa.Column("area", case_area, nullable=True))
    op.add_column("cases", sa.Column("matter", sa.String(length=255), nullable=True))
    op.add_column(
        "cases",
        sa.Column("current_module", module_name, server_default="intake", nullable=False),
    )
    op.add_column(
        "cases",
        sa.Column(
            "human_review_required",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_cases_client_id_clients", "cases", "clients", ["client_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index(op.f("ix_cases_client_id"), "cases", ["client_id"], unique=False)

    # --- audit_logs.case_id passa a ser opcional (ações sem caso, ex.: cliente) ---
    op.alter_column("audit_logs", "case_id", existing_type=sa.UUID(), nullable=True)

    # --- case_intakes ---
    op.create_table(
        "case_intakes",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("submitted_by", sa.UUID(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("estimated_loss_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("incident_date", sa.Date(), nullable=True),
        sa.Column("has_police_report", sa.Boolean(), nullable=True),
        sa.Column(
            "claimed_documents",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "pending_information",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", name="uq_case_intakes_case_id"),
    )
    op.create_index(op.f("ix_case_intakes_tenant_id"), "case_intakes", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_case_intakes_case_id"), "case_intakes", ["case_id"], unique=False)

    # --- case_documents (checklist) ---
    # Cria o tipo explicitamente e depois referencia com create_type=False na
    # coluna: op.create_table dispara seu próprio evento de criação de ENUM
    # para tipos com create_type=True (padrão), o que duplicaria o CREATE TYPE
    # acima e estouraria DuplicateObjectError — diferente de op.add_column
    # (ver "current_module"/"area" acima e migration 2a52a1908f9a), que não
    # dispara esse evento.
    document_checklist_status = postgresql.ENUM(
        "received", "pending", "waived", name="document_checklist_status"
    )
    document_checklist_status.create(op.get_bind(), checkfirst=True)
    document_checklist_status_col = postgresql.ENUM(
        "received", "pending", "waived", name="document_checklist_status", create_type=False
    )

    op.create_table(
        "case_documents",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", document_checklist_status_col, server_default="pending", nullable=False
        ),
        sa.Column("origin", sa.String(length=50), server_default="intake", nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "name", name="uq_case_documents_case_id_name"),
    )
    op.create_index(
        op.f("ix_case_documents_tenant_id"), "case_documents", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_case_documents_case_id"), "case_documents", ["case_id"], unique=False)

    # --- Row Level Security (mesmo padrão de 0406e102877a/3abdfd696724/e5c113039c58) ---
    for table in _RLS_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(_RLS_TABLES):
        _disable_tenant_rls(table)

    op.drop_index(op.f("ix_case_documents_case_id"), table_name="case_documents")
    op.drop_index(op.f("ix_case_documents_tenant_id"), table_name="case_documents")
    op.drop_table("case_documents")
    op.execute("DROP TYPE IF EXISTS document_checklist_status")

    op.drop_index(op.f("ix_case_intakes_case_id"), table_name="case_intakes")
    op.drop_index(op.f("ix_case_intakes_tenant_id"), table_name="case_intakes")
    op.drop_table("case_intakes")

    op.alter_column("audit_logs", "case_id", existing_type=sa.UUID(), nullable=False)

    op.drop_index(op.f("ix_cases_client_id"), table_name="cases")
    op.drop_constraint("fk_cases_client_id_clients", "cases", type_="foreignkey")
    op.drop_column("cases", "human_review_required")
    op.drop_column("cases", "current_module")
    op.drop_column("cases", "matter")
    op.drop_column("cases", "area")
    op.drop_column("cases", "client_id")
    op.execute("DROP TYPE IF EXISTS case_area")

    op.drop_index(op.f("ix_clients_tenant_id"), table_name="clients")
    op.drop_table("clients")
