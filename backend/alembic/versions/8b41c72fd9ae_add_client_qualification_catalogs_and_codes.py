"""add client qualification, classification catalogs and human-readable codes

Revision ID: 8b41c72fd9ae
Revises: 012bbc9b0b87
Create Date: 2026-08-07 10:12:33.401255

Fase 2.7 — o cliente deixa de ser um UUID solto na abertura do caso:

- clients: ganha `code` legível (CLI-000042) e a qualificação que a peça exige
  (CPC art. 319, II) — natureza PF/PJ, RG, nascimento, nacionalidade, estado
  civil, profissão e endereço, cujo município define o foro do consumidor
  (CDC art. 101, I).
- platforms / fraud_modalities: catálogos de classificação por tenant. A
  plataforma deixa de ser texto livre e a modalidade deixa de ser um enum
  fechado; `cases.platform` e `cases.fraud_type` permanecem como rótulo e
  família denormalizados da entrada escolhida, para que grafo, prompts e seeds
  continuem lendo os mesmos campos.
- tenant_counters: contagem sequencial por escritório, origem dos códigos
  (uma SEQUENCE do Postgres é global e faria o segundo escritório começar do
  número em que o primeiro parou).
- cases: ganha `code` (CAS-2026-000123), `platform_id` e `fraud_modality_id`.

Duas ordens importam aqui:

1. A RLS das tabelas novas é habilitada **no fim** do upgrade, depois do
   backfill — as políticas usam app.current_tenant e FORCE ROW LEVEL SECURITY
   vale inclusive para o dono da tabela.
2. O backfill roda **tenant a tenant**, setando app.current_tenant a cada
   volta, porque clients/cases já estão sob RLS desde 41280d8b096c: sem isso a
   migration enxergaria zero linhas e o SET NOT NULL de `code` estouraria.
   Mesmo padrão da migration de seed 48c0ad76f3dd (que também usa
   app.bootstrap para ler `tenants`, tabela sem policy de tenant_isolation
   utilizável fora de uma request autenticada).
"""

import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.catalog_defaults import DEFAULT_FRAUD_MODALITIES, DEFAULT_PLATFORMS
from app.core.identifiers import CodeScope, format_code

# revision identifiers, used by Alembic.
revision: str = "8b41c72fd9ae"
down_revision: Union[str, Sequence[str], None] = "012bbc9b0b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_RLS_TABLES = ("tenant_counters", "platforms", "fraud_modalities")

_OFFICE_TIMEZONE = "America/Sao_Paulo"

#: Plataformas gravadas como texto livre antes desta migration que correspondem
#: a uma entrada do catálogo padrão sob outro nome. O que não casar aqui nem
#: por label vira entrada própria do escritório (is_system=false), para que
#: nenhum caso existente perca a classificação que já tinha.
_LEGACY_PLATFORM_ALIASES = {
    "pix": "instituicao_financeira",
    "facebook marketplace": "facebook_marketplace",
    "facebook": "meta_facebook",
    "meta": "meta_facebook",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    """Converte um rótulo livre em slug ASCII (ex.: "Mercado Livre" -> "mercado_livre")."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return _NON_ALNUM.sub("_", normalized.lower()).strip("_") or "plataforma"


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


def _create_catalog_tables() -> None:
    """Cria platforms e fraud_modalities (mesmas colunas, exceto family)."""
    fraud_type_col = postgresql.ENUM(
        "pix",
        "marketplace",
        "fake_profile",
        "fake_lawyer",
        "other",
        name="fraud_type",
        create_type=False,
    )

    for table, extra_columns in (
        ("platforms", []),
        ("fraud_modalities", [sa.Column("family", fraud_type_col, nullable=False)]),
    ):
        op.create_table(
            table,
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("slug", sa.String(length=60), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            *extra_columns,
            sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "id",
                sa.UUID(),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "slug", name=f"uq_{table}_tenant_id_slug"),
        )
        op.create_index(op.f(f"ix_{table}_tenant_id"), table, ["tenant_id"], unique=False)


def _scope_to_tenant(bind: sa.Connection, tenant_id: str) -> None:
    """Aponta app.current_tenant para um escritório, satisfazendo a RLS de clients/cases."""
    bind.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
        {"tenant_id": tenant_id},
    )


def _list_tenant_ids(bind: sa.Connection) -> list[str]:
    """Lista os escritórios existentes usando o bypass de bootstrap de `tenants`."""
    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'true', false)"))
    try:
        return [str(row) for row in bind.execute(sa.text("SELECT id FROM tenants")).scalars()]
    finally:
        bind.execute(sa.text("SELECT set_config('app.bootstrap', 'false', false)"))


def _seed_catalogs(bind: sa.Connection, tenant_id: str) -> None:
    """Semeia o catálogo padrão em um escritório."""
    for entry in DEFAULT_PLATFORMS:
        bind.execute(
            sa.text(
                "INSERT INTO platforms (tenant_id, slug, label, is_system, sort_order) "
                "VALUES (:tenant_id, :slug, :label, true, :sort_order) "
                "ON CONFLICT (tenant_id, slug) DO NOTHING"
            ),
            {
                "tenant_id": tenant_id,
                "slug": entry.slug,
                "label": entry.label,
                "sort_order": entry.sort_order,
            },
        )
    for modality in DEFAULT_FRAUD_MODALITIES:
        bind.execute(
            sa.text(
                "INSERT INTO fraud_modalities "
                "(tenant_id, slug, label, family, is_system, sort_order) "
                "VALUES (:tenant_id, :slug, :label, :family, true, :sort_order) "
                "ON CONFLICT (tenant_id, slug) DO NOTHING"
            ),
            {
                "tenant_id": tenant_id,
                "slug": modality.slug,
                "label": modality.label,
                "family": modality.family.value,
                "sort_order": modality.sort_order,
            },
        )


def _link_cases_to_catalog(bind: sa.Connection, tenant_id: str) -> None:
    """Liga os casos de um escritório ao catálogo, sem perder a classificação atual."""
    labels = bind.execute(sa.text("SELECT DISTINCT platform FROM cases")).scalars().all()

    for platform_label in labels:
        slug = _LEGACY_PLATFORM_ALIASES.get(platform_label.strip().lower())
        if slug is None:
            # Casa por label (o rótulo do catálogo padrão) antes de inventar um
            # slug: "Mercado Livre" já existe como mercado_livre.
            slug = bind.execute(
                sa.text(
                    "SELECT slug FROM platforms "
                    "WHERE tenant_id = :tenant_id AND lower(label) = lower(:label)"
                ),
                {"tenant_id": tenant_id, "label": platform_label},
            ).scalar()
        if slug is None:
            slug = _slugify(platform_label)
            bind.execute(
                sa.text(
                    "INSERT INTO platforms (tenant_id, slug, label, is_system, sort_order) "
                    "VALUES (:tenant_id, :slug, :label, false, 500) "
                    "ON CONFLICT (tenant_id, slug) DO NOTHING"
                ),
                {"tenant_id": tenant_id, "slug": slug, "label": platform_label},
            )

        bind.execute(
            sa.text(
                "UPDATE cases SET platform_id = ("
                "  SELECT id FROM platforms WHERE tenant_id = :tenant_id AND slug = :slug"
                ") WHERE platform = :label"
            ),
            {"tenant_id": tenant_id, "slug": slug, "label": platform_label},
        )

    # Os slugs das modalidades padrão coincidem com os valores de FraudType,
    # então cada caso cai na entrada canônica da sua própria família.
    bind.execute(
        sa.text(
            "UPDATE cases c SET fraud_modality_id = ("
            "  SELECT m.id FROM fraud_modalities m "
            "  WHERE m.tenant_id = :tenant_id AND m.slug = c.fraud_type::text"
            ")"
        ),
        {"tenant_id": tenant_id},
    )


def _backfill_codes(bind: sa.Connection, tenant_id: str) -> None:
    """Emite códigos legíveis para os clientes e casos de um escritório, por ordem de criação."""
    counters: dict[tuple[str, int], int] = {}

    clients = (
        bind.execute(sa.text("SELECT id::text FROM clients ORDER BY created_at, id"))
        .scalars()
        .all()
    )
    for position, client_id in enumerate(clients, start=1):
        counters[(CodeScope.CLIENT.scope, 0)] = position
        bind.execute(
            sa.text("UPDATE clients SET code = :code WHERE id = :id"),
            {
                "code": format_code(CodeScope.CLIENT, year=0, value=position),
                "id": client_id,
            },
        )

    cases = bind.execute(
        sa.text(
            "SELECT id::text, "
            f"EXTRACT(YEAR FROM created_at AT TIME ZONE '{_OFFICE_TIMEZONE}')::int AS year "
            "FROM cases ORDER BY created_at, id"
        )
    ).all()
    for case_id, year in cases:
        key = (CodeScope.CASE.scope, year)
        counters[key] = counters.get(key, 0) + 1
        bind.execute(
            sa.text("UPDATE cases SET code = :code WHERE id = :id"),
            {
                "code": format_code(CodeScope.CASE, year=year, value=counters[key]),
                "id": case_id,
            },
        )

    for (scope, year), last_value in counters.items():
        bind.execute(
            sa.text(
                "INSERT INTO tenant_counters (tenant_id, scope, year, last_value) "
                "VALUES (:tenant_id, :scope, :year, :last_value) "
                "ON CONFLICT (tenant_id, scope, year) DO UPDATE SET last_value = :last_value"
            ),
            {
                "tenant_id": tenant_id,
                "scope": scope,
                "year": year,
                "last_value": last_value,
            },
        )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # --- enums novos da qualificação do cliente ---
    person_type = postgresql.ENUM("individual", "company", name="person_type")
    person_type.create(bind, checkfirst=True)
    marital_status = postgresql.ENUM(
        "single",
        "married",
        "divorced",
        "widowed",
        "separated",
        "stable_union",
        name="marital_status",
    )
    marital_status.create(bind, checkfirst=True)

    # --- tenant_counters ---
    op.create_table(
        "tenant_counters",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "scope", "year", name="pk_tenant_counters"),
    )

    _create_catalog_tables()

    # --- clients: código + qualificação ---
    op.add_column("clients", sa.Column("code", sa.String(length=20), nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "person_type",
            postgresql.ENUM("individual", "company", name="person_type", create_type=False),
            server_default="individual",
            nullable=False,
        ),
    )
    for column, type_ in (
        ("rg", sa.String(length=32)),
        ("rg_issuer", sa.String(length=32)),
        ("birth_date", sa.Date()),
        ("nationality", sa.String(length=60)),
        ("profession", sa.String(length=120)),
        ("address_street", sa.String(length=255)),
        ("address_number", sa.String(length=20)),
        ("address_complement", sa.String(length=120)),
        ("address_district", sa.String(length=120)),
        ("address_city", sa.String(length=120)),
        ("address_state", sa.String(length=2)),
        ("address_zip_code", sa.String(length=8)),
    ):
        op.add_column("clients", sa.Column(column, type_, nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "marital_status",
            postgresql.ENUM(
                "single",
                "married",
                "divorced",
                "widowed",
                "separated",
                "stable_union",
                name="marital_status",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # --- cases: código + classificação por catálogo ---
    op.add_column("cases", sa.Column("code", sa.String(length=20), nullable=True))
    op.add_column("cases", sa.Column("platform_id", sa.UUID(), nullable=True))
    op.add_column("cases", sa.Column("fraud_modality_id", sa.UUID(), nullable=True))

    # --- backfill, tenant a tenant (ver nota 2 na docstring do módulo) ---
    for tenant_id in _list_tenant_ids(bind):
        _scope_to_tenant(bind, tenant_id)
        _seed_catalogs(bind, tenant_id)
        _link_cases_to_catalog(bind, tenant_id)
        _backfill_codes(bind, tenant_id)
    bind.execute(sa.text("SELECT set_config('app.current_tenant', '', false)"))

    # --- restrições que só valem depois do backfill ---
    op.alter_column("clients", "code", existing_type=sa.String(length=20), nullable=False)
    op.create_unique_constraint("uq_clients_tenant_id_code", "clients", ["tenant_id", "code"])

    op.alter_column("cases", "code", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("cases", "platform_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column("cases", "fraud_modality_id", existing_type=sa.UUID(), nullable=False)
    op.create_unique_constraint("uq_cases_tenant_id_code", "cases", ["tenant_id", "code"])
    op.create_foreign_key(
        "fk_cases_platform_id_platforms",
        "cases",
        "platforms",
        ["platform_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_cases_fraud_modality_id_fraud_modalities",
        "cases",
        "fraud_modalities",
        ["fraud_modality_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_cases_platform_id"), "cases", ["platform_id"], unique=False)
    op.create_index(
        op.f("ix_cases_fraud_modality_id"), "cases", ["fraud_modality_id"], unique=False
    )

    for table in _RLS_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(_RLS_TABLES):
        _disable_tenant_rls(table)

    op.drop_index(op.f("ix_cases_fraud_modality_id"), table_name="cases")
    op.drop_index(op.f("ix_cases_platform_id"), table_name="cases")
    op.drop_constraint("fk_cases_fraud_modality_id_fraud_modalities", "cases", type_="foreignkey")
    op.drop_constraint("fk_cases_platform_id_platforms", "cases", type_="foreignkey")
    op.drop_constraint("uq_cases_tenant_id_code", "cases", type_="unique")
    op.drop_column("cases", "fraud_modality_id")
    op.drop_column("cases", "platform_id")
    op.drop_column("cases", "code")

    op.drop_constraint("uq_clients_tenant_id_code", "clients", type_="unique")
    for column in (
        "marital_status",
        "address_zip_code",
        "address_state",
        "address_city",
        "address_district",
        "address_complement",
        "address_number",
        "address_street",
        "profession",
        "nationality",
        "birth_date",
        "rg_issuer",
        "rg",
        "person_type",
        "code",
    ):
        op.drop_column("clients", column)

    for table in ("fraud_modalities", "platforms"):
        op.drop_index(op.f(f"ix_{table}_tenant_id"), table_name=table)
        op.drop_table(table)
    op.drop_table("tenant_counters")

    op.execute("DROP TYPE IF EXISTS marital_status")
    op.execute("DROP TYPE IF EXISTS person_type")
