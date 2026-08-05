"""Testes de multitenancy e RLS (CLAUDE.md, seção 7 — regra crítica).

Cobre duas camadas de isolamento: o TenantMiddleware (aplicação) e a Row
Level Security do Postgres (banco) — violação de qualquer uma das duas é
bug crítico segundo o CLAUDE.md.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.db import (
    async_session_factory,
    get_session,
    scope_session_to_auth_bootstrap,
    scope_session_to_tenant,
)
from app.models.case import Case
from app.models.enums import FraudType, UrgencyLevel
from tests.conftest import TenantFixture, login


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
        scope_session_to_tenant(session, tenant.tenant_id)
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
        scope_session_to_tenant(session, other_tenant.tenant_id)
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert case_id not in visible_ids

    # Confirma que o dono enxerga o próprio caso normalmente.
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert case_id in visible_ids


async def test_rls_blocks_query_without_tenant_guc_set(tenant: TenantFixture) -> None:
    """Sem app.current_tenant definido na sessão, a RLS nega tudo (fail closed)."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        case = Case(
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            platform="shopee",
            fraud_type=FraudType.MARKETPLACE,
            urgency=UrgencyLevel.MEDIUM,
        )
        session.add(case)
        await session.commit()

    # get_session() não declara escopo de tenant nenhum, então o listener de
    # app/core/db.py aplica "sem tenant" no início da transação — o GUC
    # deixado por outra sessão na mesma conexão física nunca é herdado.
    async for session in get_session():
        visible_ids = (await session.scalars(select(Case.id))).all()
        assert visible_ids == []


async def test_tenant_scope_is_reapplied_after_commit_on_another_connection(
    tenant: TenantFixture,
) -> None:
    """Regressão do HTTP 500 em POST /cases (refresh após commit).

    Ao dar `commit()`, a sessão devolve a conexão física ao pool; a instrução
    seguinte — aqui o SELECT de `session.refresh()` — pode sair por OUTRA
    conexão, cujo app.current_tenant é resíduo de outra request (ex.: o ''
    de `get_auth_bootstrap_session` no /auth/login). Sem reaplicar o escopo
    por transação, a RLS esconde a linha recém-inserida e o refresh estoura.
    """

    # Segura várias sessões de bootstrap ao mesmo tempo para o pool crescer e
    # ficar com conexões cujo app.current_tenant é '' (como faz o login).
    async def _hold_bootstrap_connection() -> None:
        async with async_session_factory() as session:
            scope_session_to_auth_bootstrap(session)
            await session.execute(select(1))
            await asyncio.sleep(0.2)

    await asyncio.gather(*(_hold_bootstrap_connection() for _ in range(5)))

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        case = Case(
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            platform="mercado livre",
            fraud_type=FraudType.MARKETPLACE,
            urgency=UrgencyLevel.MEDIUM,
        )
        session.add(case)
        await session.commit()

        # Falhava com InvalidRequestError("Could not refresh instance") antes
        # da correção — a linha existia, mas a RLS a escondia na nova conexão.
        await session.refresh(case)
        assert case.platform == "mercado livre"


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
