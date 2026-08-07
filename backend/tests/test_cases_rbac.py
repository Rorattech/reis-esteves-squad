"""Testes de RBAC nas rotas de caso (CLAUDE.md, seção 12 — admin | lawyer | paralegal | viewer)."""

from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import TenantFixture, case_payload, login


async def test_viewer_cannot_create_case(
    api_client: AsyncClient, viewer_tenant: TenantFixture
) -> None:
    headers = await login(api_client, viewer_tenant)
    response = await api_client.post(
        "/api/v1/cases", json=await case_payload(api_client, headers), headers=headers
    )
    assert response.status_code == 403


async def test_admin_can_create_case(api_client: AsyncClient, tenant: TenantFixture) -> None:
    headers = await login(api_client, tenant)
    response = await api_client.post(
        "/api/v1/cases", json=await case_payload(api_client, headers), headers=headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["platform"] == "WhatsApp"
    assert body["code"].startswith("CAS-")


async def test_viewer_can_list_cases(
    api_client: AsyncClient, tenant: TenantFixture, viewer_tenant: TenantFixture
) -> None:
    # viewer só não pode ESCREVER — leitura continua liberada para todos os papéis.
    headers = await login(api_client, viewer_tenant)
    response = await api_client.get("/api/v1/cases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_viewer_cannot_update_case(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    viewer_tenant: TenantFixture,
) -> None:
    # Um viewer do MESMO tenant do caso ainda assim não pode editar — RBAC é
    # sobre papel, não sobre dono do recurso.
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
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


async def test_admin_can_delete_own_case(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    response = await api_client.delete(f"/api/v1/cases/{tenant_with_case.case_id}", headers=headers)
    assert response.status_code == 204, response.text

    # O caso realmente sumiu para o tenant.
    follow_up = await api_client.get(f"/api/v1/cases/{tenant_with_case.case_id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_keeps_the_audit_trail_of_the_deletion(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    """A exclusão do caso não pode apagar o registro de que ele foi excluído."""
    headers = await login(api_client, tenant_with_case)
    await api_client.delete(f"/api/v1/cases/{tenant_with_case.case_id}", headers=headers)

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        actions = (
            await session.scalars(
                select(AuditLog.action).where(AuditLog.tenant_id == tenant_with_case.tenant_id)
            )
        ).all()
    assert "excluiu o caso" in actions


async def test_paralegal_cannot_delete_case(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    """Excluir é mais restrito que editar: paralegal escreve, mas não exclui."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        session.add(
            User(
                tenant_id=tenant_with_case.tenant_id,
                email="paralegal-delete@pytestsquad.example.com.br",
                hashed_password=hash_password("senha-de-teste-123"),
                role=UserRole.PARALEGAL,
            )
        )
        await session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "paralegal-delete@pytestsquad.example.com.br",
            "password": "senha-de-teste-123",
        },
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = await api_client.delete(f"/api/v1/cases/{tenant_with_case.case_id}", headers=headers)
    assert response.status_code == 403


async def test_cannot_delete_case_of_another_tenant(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    other_tenant: TenantFixture,
) -> None:
    headers = await login(api_client, other_tenant)
    response = await api_client.delete(f"/api/v1/cases/{tenant_with_case.case_id}", headers=headers)
    assert response.status_code == 404
