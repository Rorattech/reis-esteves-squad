"""add auth bootstrap rls policy

Revision ID: 3abdfd696724
Revises: 0406e102877a
Create Date: 2026-07-28 03:02:46.045522

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3abdfd696724"
down_revision: Union[str, Sequence[str], None] = "0406e102877a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# tenants/users são as únicas tabelas tocadas pelo bootstrap de autenticação
# (POST /auth/register, /auth/login, /auth/refresh) — cases e audit_logs nunca
# recebem essa policy, então continuam bloqueadas por tenant_isolation mesmo
# que app.bootstrap fique 'true' por engano em alguma sessão.
_BOOTSTRAP_TABLES = ("tenants", "users")

_ORIGINAL_TENANT_ISOLATION_EXPR = "current_setting('app.current_tenant', true)::uuid"
# NULLIF(..., '') é necessário porque RESET/set_config(..., NULL, ...) em um
# GUC customizado (placeholder, não registrado por uma extensão C) não volta a
# NULL no Postgres — vira '' —, e ''::uuid estoura "invalid input syntax for
# type uuid", derrubando a request com 500 em vez de simplesmente negar acesso
# (ver app/core/db.py, get_session/get_auth_bootstrap_session).
_HARDENED_TENANT_ISOLATION_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    """Upgrade schema.

    Dois ajustes na RLS herdada de 0406e102877a:

    1. Endurece tenant_isolation para tolerar app.current_tenant = '' (GUC
       "resetado") sem estourar erro de cast — passa a negar acesso (fail
       closed) igual a quando o GUC nunca foi definido.
    2. Cria a policy auth_bootstrap em tenants/users: a policy tenant_isolation
       exige app.current_tenant já definido, o que é estruturalmente
       impossível durante o registro de um tenant novo (ele ainda não existe)
       e durante o login (o tenant do usuário ainda não é conhecido, a busca é
       por e-mail). Como policies PERMISSIVE do Postgres se combinam por OR,
       esta policy adicional libera acesso quando app.bootstrap = 'true' — um
       GUC de sessão setado apenas por get_auth_bootstrap_session
       (backend/app/core/db.py), nunca por entrada do cliente.

    Ver CLAUDE.md, seção 7.
    """
    op.execute(
        f"ALTER POLICY tenant_isolation ON tenants "
        f"USING (id = {_HARDENED_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (id = {_HARDENED_TENANT_ISOLATION_EXPR})"
    )
    for table in ("users", "cases", "audit_logs"):
        op.execute(
            f"ALTER POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = {_HARDENED_TENANT_ISOLATION_EXPR}) "
            f"WITH CHECK (tenant_id = {_HARDENED_TENANT_ISOLATION_EXPR})"
        )

    for table in _BOOTSTRAP_TABLES:
        op.execute(
            f"CREATE POLICY auth_bootstrap ON {table} "
            "FOR ALL "
            "USING (current_setting('app.bootstrap', true) = 'true') "
            "WITH CHECK (current_setting('app.bootstrap', true) = 'true')"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in _BOOTSTRAP_TABLES:
        op.execute(f"DROP POLICY IF EXISTS auth_bootstrap ON {table}")

    op.execute(
        f"ALTER POLICY tenant_isolation ON tenants "
        f"USING (id = {_ORIGINAL_TENANT_ISOLATION_EXPR}) "
        f"WITH CHECK (id = {_ORIGINAL_TENANT_ISOLATION_EXPR})"
    )
    for table in ("users", "cases", "audit_logs"):
        op.execute(
            f"ALTER POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = {_ORIGINAL_TENANT_ISOLATION_EXPR}) "
            f"WITH CHECK (tenant_id = {_ORIGINAL_TENANT_ISOLATION_EXPR})"
        )
