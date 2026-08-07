"""Testes de isolamento de tenant (RLS) para o domínio da Fase 2 — Intake.

Cobre as tabelas novas (clients, case_intakes, case_documents) e a
validação de aplicação que impede vincular um caso ao client_id de outro
tenant (CLAUDE.md, seção 7 — regra crítica).
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.core.identifiers import CodeScope, next_code
from app.models.case_document import CaseDocument
from app.models.case_intake import CaseIntake
from app.models.client import Client
from tests.conftest import TenantFixture, case_payload, login


async def test_rls_blocks_cross_tenant_read_of_clients(
    tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        client = Client(
            tenant_id=tenant.tenant_id,
            code=await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CLIENT),
            full_name="Cliente do Tenant A",
        )
        session.add(client)
        await session.commit()
        client_id = client.id

    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        visible_ids = (await session.scalars(select(Client.id))).all()
        assert client_id not in visible_ids


async def test_rls_blocks_cross_tenant_read_of_case_intakes(
    tenant_with_case: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        intake = CaseIntake(
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            submitted_by=tenant_with_case.user_id,
            narrative="Relato confidencial do tenant A.",
        )
        session.add(intake)
        await session.commit()
        intake_id = intake.id

    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        visible_ids = (await session.scalars(select(CaseIntake.id))).all()
        assert intake_id not in visible_ids


async def test_rls_blocks_cross_tenant_read_of_case_documents(
    tenant_with_case: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        item = CaseDocument(
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            name="Documento do tenant A",
        )
        session.add(item)
        await session.commit()
        item_id = item.id

    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        visible_ids = (await session.scalars(select(CaseDocument.id))).all()
        assert item_id not in visible_ids


async def test_api_rejects_case_creation_with_client_id_of_another_tenant(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        foreign_client = Client(
            tenant_id=other_tenant.tenant_id,
            code=await next_code(session, tenant_id=other_tenant.tenant_id, scope=CodeScope.CLIENT),
            full_name="Cliente de Outro Tenant",
        )
        session.add(foreign_client)
        await session.commit()
        foreign_client_id = str(foreign_client.id)

    headers = await login(api_client, tenant)
    response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, client_id=foreign_client_id),
        headers=headers,
    )
    assert response.status_code == 404


async def test_api_accepts_case_creation_with_client_id_of_same_tenant(
    api_client: AsyncClient, tenant_with_client: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_client)
    response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, client_id=str(tenant_with_client.client_id)),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["client_id"] == str(tenant_with_client.client_id)
