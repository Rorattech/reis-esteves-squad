"""seed reis esteves dev tenant

Revision ID: d27cf82e3178
Revises: e5c113039c58
Create Date: 2026-07-29 10:00:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.core.config import settings
from app.core.security import hash_password

# revision identifiers, used by Alembic.
revision: str = "d27cf82e3178"
down_revision: Union[str, Sequence[str], None] = "e5c113039c58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Credenciais de teste conhecidas por todo o time — nunca usar fora de dev.
_TENANT_NAME = "Reis Esteves Advocacia"
_TENANT_SLUG = "reis-esteves"
_ADMIN_EMAIL = "admin@reisesteves.com.br"
_ADMIN_PASSWORD = "ReisEsteves2026!"


def upgrade() -> None:
    """Semeia o tenant Reis Esteves + 1 usuário admin, só em ambiente de dev.

    Existe como migration (não como script de seed separado) a pedido do
    time, para todo dev que rodar `alembic upgrade head` num banco novo já
    ter esse tenant/usuário prontos para testar autenticação manualmente.

    Guardas de segurança:
    - Só roda se BACKEND_ENV=development — um usuário admin com senha
      conhecida por todo o time nunca pode existir fora do ambiente local
      (CLAUDE.md, seção 12).
    - Idempotente (ON CONFLICT) — seguro rodar `alembic upgrade head` de novo
      num banco que já tem esse tenant, sem duplicar nem estourar erro.
    - Usa app.bootstrap=true (mesma policy `auth_bootstrap` que /auth/register
      usa — ver migration 3abdfd696724) porque a role da aplicação (DB_USER)
      não é superuser e está sujeita à RLS mesmo dentro de uma migration.
    """
    if settings.backend_env != "development":
        return

    bind = op.get_bind()
    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'true', false)"))

    tenant_id = bind.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug) "
            "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug "
            "RETURNING id"
        ),
        {"id": str(uuid.uuid4()), "name": _TENANT_NAME, "slug": _TENANT_SLUG},
    ).scalar_one()

    bind.execute(
        sa.text(
            "INSERT INTO users (id, tenant_id, email, hashed_password, role) "
            "VALUES (:id, :tenant_id, :email, :hashed_password, 'admin') "
            "ON CONFLICT (tenant_id, email) DO NOTHING"
        ),
        {
            "id": str(uuid.uuid4()),
            "tenant_id": str(tenant_id),
            "email": _ADMIN_EMAIL,
            "hashed_password": hash_password(_ADMIN_PASSWORD),
        },
    )


def downgrade() -> None:
    """Remove o tenant/usuário semeados (cascade cuida do resto), só em dev."""
    if settings.backend_env != "development":
        return

    bind = op.get_bind()
    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'true', false)"))
    bind.execute(sa.text("DELETE FROM tenants WHERE slug = :slug"), {"slug": _TENANT_SLUG})
