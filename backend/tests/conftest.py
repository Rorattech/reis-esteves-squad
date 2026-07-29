"""Fixtures compartilhadas dos testes de backend.

Roda contra o Postgres real (CLAUDE.md, seção 15 — nunca SQLite), usando as
migrations já aplicadas ao banco de desenvolvimento. Cada teste cria seu
próprio tenant com slug único e o remove no teardown — os testes nunca
tocam dados de outros tenants nem deixam resíduo no banco.
"""

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path


def _load_repo_root_env() -> None:
    """Popula variáveis do .env da raiz do repo, sem sobrescrever env vars já definidas.

    Necessário porque `Settings` (app/core/config.py) só enxerga um `.env` no
    diretório de execução atual — quando os testes rodam de dentro de
    backend/ (fora do container, ver backend/Dockerfile), esse arquivo não
    existe ali; o real está na raiz do repo.
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_repo_root_env()

import pytest_asyncio  # noqa: E402 — precisa vir depois de _load_repo_root_env()
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import async_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.enums import FraudType, UrgencyLevel, UserRole  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402

_RESET_GUCS = (
    "SELECT set_config('app.current_tenant', '', false), "
    "set_config('app.bootstrap', 'true', false)"
)
_SET_TENANT_GUC = (
    "SELECT set_config('app.current_tenant', :t, false), "
    "set_config('app.bootstrap', 'false', false)"
)


class TenantFixture:
    """Dados de um tenant de teste, com um usuário admin já criado."""

    def __init__(self, tenant_id: uuid.UUID, user_id: uuid.UUID, email: str, password: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.email = email
        self.password = password
        self.case_id: uuid.UUID | None = None
        self.client_id: uuid.UUID | None = None


async def _create_tenant(role: UserRole = UserRole.ADMIN) -> TenantFixture:
    suffix = uuid.uuid4().hex[:12]
    email = f"user-{suffix}@pytestsquad.example.com.br"
    password = "senha-de-teste-123"

    async with async_session_factory() as session:
        await session.execute(text(_RESET_GUCS))
        tenant_row = Tenant(name=f"Tenant Pytest {suffix}", slug=f"pytest-{suffix}")
        session.add(tenant_row)
        await session.flush()

        user_row = User(
            tenant_id=tenant_row.id,
            email=email,
            hashed_password=hash_password(password),
            role=role,
        )
        session.add(user_row)
        await session.flush()
        await session.commit()
        return TenantFixture(
            tenant_id=tenant_row.id, user_id=user_row.id, email=email, password=password
        )


async def _delete_tenant(tenant_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_RESET_GUCS))
        await session.execute(
            text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": str(tenant_id)}
        )
        await session.commit()


@pytest_asyncio.fixture
async def tenant() -> AsyncIterator[TenantFixture]:
    """Tenant de teste com um usuário admin — removido (cascade) ao final do teste."""
    fixture = await _create_tenant(UserRole.ADMIN)
    try:
        yield fixture
    finally:
        await _delete_tenant(fixture.tenant_id)


@pytest_asyncio.fixture
async def other_tenant() -> AsyncIterator[TenantFixture]:
    """Segundo tenant de teste, para casos de isolamento cross-tenant."""
    fixture = await _create_tenant(UserRole.ADMIN)
    try:
        yield fixture
    finally:
        await _delete_tenant(fixture.tenant_id)


@pytest_asyncio.fixture
async def viewer_tenant() -> AsyncIterator[TenantFixture]:
    """Tenant de teste cujo único usuário tem papel viewer (somente leitura)."""
    fixture = await _create_tenant(UserRole.VIEWER)
    try:
        yield fixture
    finally:
        await _delete_tenant(fixture.tenant_id)


@pytest_asyncio.fixture
async def tenant_with_client(tenant: TenantFixture) -> TenantFixture:
    """Tenant de teste com um cliente já cadastrado (útil para testes de intake)."""
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        client = Client(tenant_id=tenant.tenant_id, full_name="Cliente Pytest")
        session.add(client)
        await session.commit()
        await session.refresh(client)
        tenant.client_id = client.id
    return tenant


@pytest_asyncio.fixture
async def tenant_with_case(tenant: TenantFixture) -> TenantFixture:
    """Tenant de teste com um caso já criado (útil para testes de leitura/RBAC)."""
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        case = Case(
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            platform="whatsapp",
            fraud_type=FraudType.PIX,
            urgency=UrgencyLevel.HIGH,
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)
        tenant.case_id = case.id
    return tenant


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """Cliente HTTP assíncrono ligado direto na app FastAPI (sem subir servidor)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def login(api_client: AsyncClient, tenant: TenantFixture) -> dict[str, str]:
    """Faz login com as credenciais de `tenant` e retorna o header Authorization."""
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": tenant.email, "password": tenant.password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth_headers(api_client: AsyncClient, tenant: TenantFixture) -> dict[str, str]:
    """Cabeçalho Authorization com um access token válido para `tenant`."""
    return await login(api_client, tenant)
