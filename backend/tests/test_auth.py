"""Testes do fluxo de autenticação: registro, login, refresh e /me (CLAUDE.md, seção 12)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import async_session_factory
from app.models.tenant import Tenant
from tests.conftest import _RESET_GUCS, _SET_TENANT_GUC, TenantFixture, login


async def _delete_tenant_by_id(tenant_id: str) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_RESET_GUCS))
        await session.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant_id})
        await session.commit()


async def test_register_creates_tenant_and_admin_user(api_client: AsyncClient) -> None:
    slug = f"pytest-register-{uuid.uuid4().hex[:10]}"
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Escritorio Registrado no Teste",
            "tenant_slug": slug,
            "admin_email": f"{slug}@pytestsquad.example.com.br",
            "admin_password": "senha-valida-123",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == f"{slug}@pytestsquad.example.com.br"
    assert body["role"] == "admin"
    assert "hashed_password" not in body

    await _delete_tenant_by_id(body["tenant_id"])


async def test_register_rejects_duplicate_slug(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        existing_slug = (
            await session.scalars(select(Tenant.slug).where(Tenant.id == tenant.tenant_id))
        ).one()

    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Outro Nome",
            "tenant_slug": existing_slug,
            "admin_email": "outro@pytestsquad.example.com.br",
            "admin_password": "senha-valida-123",
        },
    )
    assert response.status_code == 409


async def test_login_success_returns_tokens(api_client: AsyncClient, tenant: TenantFixture) -> None:
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": tenant.email, "password": tenant.password}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": tenant.email, "password": "senha-errada"}
    )
    assert response.status_code == 401


async def test_login_unknown_email_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "ninguem@pytestsquad.example.com.br", "password": "qualquer-coisa"},
    )
    assert response.status_code == 401


async def test_refresh_issues_new_access_token(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    login_response = await api_client.post(
        "/api/v1/auth/login", json={"email": tenant.email, "password": tenant.password}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


async def test_refresh_rejects_access_token(api_client: AsyncClient, tenant: TenantFixture) -> None:
    login_response = await api_client.post(
        "/api/v1/auth/login", json={"email": tenant.email, "password": tenant.password}
    )
    access_token = login_response.json()["access_token"]

    # access_token não é refresh_token — decode_token deve rejeitar por tipo errado.
    response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


async def test_refresh_rejects_garbage_token(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "isto-nao-e-um-jwt"}
    )
    assert response.status_code == 401


async def test_me_returns_authenticated_user(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    headers = await login(api_client, tenant)
    response = await api_client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == tenant.email
    assert body["tenant_id"] == str(tenant.tenant_id)


async def test_me_without_token_is_forbidden(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 403
