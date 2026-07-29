"""Testes de multitenancy e RLS (CLAUDE.md, seção 7 — regra crítica).

Cobre duas camadas de isolamento: o TenantMiddleware (aplicação) e a Row
Level Security do Postgres (banco) — violação de qualquer uma das duas é
bug crítico segundo o CLAUDE.md.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import async_session_factory, get_session
from app.models.case import Case
from app.models.enums import FraudType, UrgencyLevel
from tests.conftest import _SET_TENANT_GUC, TenantFixture, login


async def test_protected_route_without_token_is_forbidden(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/cases")
    assert response.status_code == 403


async def test_protected_route_with_malformed_bearer_is_forbidden(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/cases", headers={"Authorization": "Bearer isto-nao-e-um-jwt-valido"}
    )
    assert response.status_code == 403


async def test_protected_route_with_token_missing_tenant_id_is_forbidden(
    api_client: AsyncClient,
) -> None:
    # Token assinado com a mesma secret key, mas sem o claim tenant_id — o
    # TenantMiddleware deve bloquear mesmo com assinatura válida.
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.backend_secret_key,
        algorithm=settings.backend_jwt_algorithm,
    )
    response = await api_client.get("/api/v1/cases", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_protected_route_with_expired_token_is_forbidden(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired_token = jwt.encode(
        {
            "sub": str(tenant.user_id),
            "tenant_id": str(tenant.tenant_id),
            "role": "admin",
            "type": "access",
            "iat": past - timedelta(minutes=15),
            "exp": past,
        },
        settings.backend_secret_key,
        algorithm=settings.backend_jwt_algorithm,
    )
    response = await api_client.get(
        "/api/v1/cases", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 403


async def test_rls_blocks_cross_tenant_read_at_db_level(
    tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    """Mesmo com uma query sem filtro de tenant_id, a RLS não deve vazar dados."""
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
        case_id = case.id

    # Sessão escopada para other_tenant: mesmo um SELECT sem WHERE tenant_id
    # não deve retornar o caso do primeiro tenant (RLS "fail closed").
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(other_tenant.tenant_id)})
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert case_id not in visible_ids

    # Confirma que o dono enxerga o próprio caso normalmente.
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert case_id in visible_ids


async def test_rls_blocks_query_without_tenant_guc_set(tenant: TenantFixture) -> None:
    """Sem app.current_tenant definido na sessão, a RLS nega tudo (fail closed)."""
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        case = Case(
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            platform="shopee",
            fraud_type=FraudType.MARKETPLACE,
            urgency=UrgencyLevel.MEDIUM,
        )
        session.add(case)
        await session.commit()

    # get_session() (não async_session_factory() direto) é o que de fato
    # reseta app.current_tenant/app.bootstrap no início da sessão — o pool
    # reutiliza conexões físicas, então uma sessão "crua" pode herdar o GUC
    # deixado por outra sessão anterior na mesma conexão (ver app/core/db.py).
    async for session in get_session():
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert visible_ids == []


async def test_api_returns_404_for_case_of_another_tenant(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    headers_a = await login(api_client, tenant)
    create_response = await api_client.post(
        "/api/v1/cases",
        json={"platform": "shopee", "fraud_type": "marketplace", "urgency": "medium"},
        headers=headers_a,
    )
    assert create_response.status_code == 201, create_response.text
    case_id = create_response.json()["id"]

    headers_b = await login(api_client, other_tenant)
    response = await api_client.get(f"/api/v1/cases/{case_id}", headers=headers_b)
    assert response.status_code == 404

    # o próprio tenant continua enxergando o caso normalmente.
    own_response = await api_client.get(f"/api/v1/cases/{case_id}", headers=headers_a)
    assert own_response.status_code == 200
