"""Testes de RBAC nas rotas de caso (CLAUDE.md, seção 12 — admin | lawyer | paralegal | viewer)."""

from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import async_session_factory
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import _SET_TENANT_GUC, TenantFixture, login

_CASE_PAYLOAD = {"platform": "shopee", "fraud_type": "marketplace", "urgency": "medium"}


async def test_viewer_cannot_create_case(
    api_client: AsyncClient, viewer_tenant: TenantFixture
) -> None:
    headers = await login(api_client, viewer_tenant)
    response = await api_client.post("/api/v1/cases", json=_CASE_PAYLOAD, headers=headers)
    assert response.status_code == 403


async def test_admin_can_create_case(api_client: AsyncClient, tenant: TenantFixture) -> None:
    headers = await login(api_client, tenant)
    response = await api_client.post("/api/v1/cases", json=_CASE_PAYLOAD, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["platform"] == "shopee"


async def test_viewer_can_list_cases(
    api_client: AsyncClient, tenant: TenantFixture, viewer_tenant: TenantFixture
) -> None:
    # viewer só não pode ESCREVER — leitura continua liberada para todos os papéis.
    headers = await login(api_client, viewer_tenant)
    response = await api_client.get("/api/v1/cases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_viewer_cannot_update_case(
    api_client: AsyncClient, tenant_with_case: TenantFixture, viewer_tenant: TenantFixture
) -> None:
    # Um viewer do MESMO tenant do caso ainda assim não pode editar — RBAC é
    # sobre papel, não sobre dono do recurso.
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        viewer_user = User(
            tenant_id=tenant_with_case.tenant_id,
            email="viewer-no-mesmo-tenant@pytestsquad.example.com.br",
            hashed_password=hash_password("senha-de-teste-123"),
            role=UserRole.VIEWER,
        )
        session.add(viewer_user)
        await session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "viewer-no-mesmo-tenant@pytestsquad.example.com.br",
            "password": "senha-de-teste-123",
        },
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = await api_client.patch(
        f"/api/v1/cases/{tenant_with_case.case_id}",
        json={"urgency": "critical"},
        headers=headers,
    )
    assert response.status_code == 403
