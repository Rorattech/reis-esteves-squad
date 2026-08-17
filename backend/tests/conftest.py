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

import pytest  # noqa: E402 — precisa vir depois de _load_repo_root_env()
import pytest_asyncio  # noqa: E402 — precisa vir depois de _load_repo_root_env()
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.db import (  # noqa: E402
    async_session_factory,
    scope_session_to_auth_bootstrap,
    scope_session_to_tenant,
)
from app.core.identifiers import CodeScope, next_code  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.catalog import FraudModality, Platform  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.enums import UrgencyLevel, UserRole  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.catalog_service import ensure_catalog_seeded  # noqa: E402

#: Entradas de catálogo padrão usadas como classificação default nos testes.
#: São slugs semeados por app/core/catalog_defaults.py.
DEFAULT_PLATFORM_SLUG = "whatsapp"
DEFAULT_MODALITY_SLUG = "pix"


class TenantFixture:
    """Dados de um tenant de teste, com um usuário admin já criado."""

    def __init__(self, tenant_id: uuid.UUID, user_id: uuid.UUID, email: str, password: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.email = email
        self.password = password
        self.case_id: uuid.UUID | None = None
        self.case_code: str | None = None
        self.client_id: uuid.UUID | None = None
        self.platform_id: uuid.UUID | None = None
        self.fraud_modality_id: uuid.UUID | None = None


async def _create_tenant(role: UserRole = UserRole.ADMIN) -> TenantFixture:
    suffix = uuid.uuid4().hex[:12]
    email = f"user-{suffix}@pytestsquad.example.com.br"
    password = "senha-de-teste-123"

    async with async_session_factory() as session:
        scope_session_to_auth_bootstrap(session)
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
        scope_session_to_auth_bootstrap(session)
        await session.execute(
            text("DELETE FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": str(tenant_id)},
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


async def seed_catalog(session, tenant_id: uuid.UUID) -> tuple[Platform, FraudModality]:
    """Semeia o catálogo do tenant e devolve as entradas padrão dos testes.

    Desde a Fase 2.7 abrir um caso exige uma entrada de `platforms` e uma de
    `fraud_modalities` do próprio escritório — não há mais texto livre nem enum
    direto (ver app/models/catalog.py).

    Args:
        session: Sessão já escopada para o tenant.
        tenant_id: Tenant de teste.

    Returns:
        A plataforma e a modalidade padrão dos testes.
    """
    await ensure_catalog_seeded(session, tenant_id=tenant_id)
    platform = await session.scalar(
        select(Platform).where(
            Platform.tenant_id == tenant_id, Platform.slug == DEFAULT_PLATFORM_SLUG
        )
    )
    modality = await session.scalar(
        select(FraudModality).where(
            FraudModality.tenant_id == tenant_id,
            FraudModality.slug == DEFAULT_MODALITY_SLUG,
        )
    )
    return platform, modality


async def create_case_row(session, tenant: TenantFixture, **overrides) -> Case:
    """Cria um `Case` completo (código + catálogo) direto no banco.

    Existe para os testes que precisam de um caso pronto sem passar pela API.
    Os campos denormalizados `platform`/`fraud_type` são derivados das entradas
    de catálogo, como a rota faz — nunca escritos direto.

    Args:
        session: Sessão já escopada para o tenant.
        tenant: Fixture do tenant dono do caso.
        **overrides: Campos a sobrescrever no `Case`.

    Returns:
        O caso criado, ainda não commitado.
    """
    platform, modality = await seed_catalog(session, tenant.tenant_id)
    fields = {
        "tenant_id": tenant.tenant_id,
        "user_id": tenant.user_id,
        "code": await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE),
        "platform_id": platform.id,
        "fraud_modality_id": modality.id,
        "platform": platform.label,
        "fraud_type": modality.family,
        "urgency": UrgencyLevel.HIGH,
    }
    fields.update(overrides)
    case = Case(**fields)
    session.add(case)
    await session.flush()
    return case


@pytest_asyncio.fixture
async def tenant_with_catalog(tenant: TenantFixture) -> TenantFixture:
    """Tenant de teste com o catálogo semeado e as entradas padrão à mão."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        platform, modality = await seed_catalog(session, tenant.tenant_id)
        await session.commit()
        tenant.platform_id = platform.id
        tenant.fraud_modality_id = modality.id
    return tenant


@pytest_asyncio.fixture
async def tenant_with_client(tenant: TenantFixture) -> TenantFixture:
    """Tenant de teste com um cliente já cadastrado (útil para testes de intake)."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        client = Client(
            tenant_id=tenant.tenant_id,
            code=await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CLIENT),
            full_name="Cliente Pytest",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        tenant.client_id = client.id
    return tenant


@pytest_asyncio.fixture
async def tenant_with_case(tenant: TenantFixture) -> TenantFixture:
    """Tenant de teste com um caso já criado (útil para testes de leitura/RBAC)."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        case = await create_case_row(session, tenant)
        await session.commit()
        await session.refresh(case)
        tenant.case_id = case.id
        tenant.case_code = case.code
        tenant.platform_id = case.platform_id
        tenant.fraud_modality_id = case.fraud_modality_id
    return tenant


async def case_payload(
    api_client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    """Monta o corpo de `POST /api/v1/cases` resolvendo o catálogo pela própria API.

    Desde a Fase 2.7 a classificação é por entrada de catálogo, e os ids são
    por tenant — nenhum teste pode ter um id fixo. Resolver via API também
    exercita o seed sob demanda de `GET /catalog/...`.

    Args:
        api_client: Cliente HTTP dos testes.
        headers: Cabeçalho Authorization do tenant.
        **overrides: Campos a sobrescrever no payload.

    Returns:
        Payload pronto para o POST.
    """
    platforms = await api_client.get("/api/v1/catalog/platforms", headers=headers)
    modalities = await api_client.get("/api/v1/catalog/fraud-modalities", headers=headers)
    assert platforms.status_code == 200, platforms.text
    assert modalities.status_code == 200, modalities.text

    payload: dict[str, object] = {
        "platform_id": next(
            entry["id"] for entry in platforms.json() if entry["slug"] == DEFAULT_PLATFORM_SLUG
        ),
        "fraud_modality_id": next(
            entry["id"] for entry in modalities.json() if entry["slug"] == DEFAULT_MODALITY_SLUG
        ),
        "urgency": "medium",
    }
    payload.update(overrides)
    return payload


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


@pytest.fixture(autouse=True)
def _offline_vision(monkeypatch) -> None:
    """Impede que qualquer teste chame a Google Cloud Vision de verdade.

    O pipeline de extração dispara em todo upload, e o upload padrão da suíte é
    um PNG — sem este guard, rodar os testes gastaria cota, exigiria uma API key
    configurada e deixaria a suíte dependente de rede. Testes que se importam
    com o conteúdo do OCR sobrescrevem isto (ver `_stub_vision` em
    tests/test_evidence_extraction.py).
    """
    from app.core import extraction, vision

    async def _annotate_image(content: bytes) -> vision.VisionAnnotation:
        return vision.VisionAnnotation(text="", confidence=0.9, pages_annotated=1)

    async def _annotate_pdf(content: bytes, *, max_pages: int) -> vision.VisionAnnotation:
        return vision.VisionAnnotation(text="", confidence=0.9, pages_annotated=1)

    monkeypatch.setattr(extraction, "annotate_image", _annotate_image)
    monkeypatch.setattr(extraction, "annotate_pdf", _annotate_pdf)
