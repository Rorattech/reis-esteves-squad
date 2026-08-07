"""Testes da emissão de códigos legíveis de caso e cliente (app/core/identifiers.py)."""

import asyncio

from app.core.db import async_session_factory, scope_session_to_tenant
from app.core.identifiers import CodeScope, current_year, format_code, next_code
from tests.conftest import TenantFixture


def test_format_code_pads_and_dates_by_scope() -> None:
    assert format_code(CodeScope.CASE, year=2026, value=123) == "CAS-2026-000123"
    # Cliente é perene: o ano não entra no código (o mesmo cliente atravessa anos).
    assert format_code(CodeScope.CLIENT, year=2026, value=42) == "CLI-000042"


async def test_sequence_starts_at_one_and_increments(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        first = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        second = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        await session.commit()

    year = current_year()
    assert first == f"CAS-{year}-000001"
    assert second == f"CAS-{year}-000002"


async def test_case_and_client_series_are_independent(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        case_code = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        client_code = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CLIENT)
        await session.commit()

    assert case_code.endswith("000001")
    assert client_code == "CLI-000001"


async def test_each_tenant_counts_from_one(
    tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    """Uma SEQUENCE do Postgres é global; a contagem tem de ser por escritório."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        for _ in range(3):
            await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        await session.commit()

    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        first_of_other = await next_code(
            session, tenant_id=other_tenant.tenant_id, scope=CodeScope.CASE
        )
        await session.commit()

    assert first_of_other == f"CAS-{current_year()}-000001"


async def test_concurrent_allocations_never_collide(tenant: TenantFixture) -> None:
    """Duas requests simultâneas do mesmo tenant não podem receber o mesmo número.

    Cada alocação abre a própria sessão (como duas requests HTTP fariam), então
    o que serializa é o row lock do ON CONFLICT DO UPDATE — não uma trava de
    aplicação.
    """

    async def allocate() -> str:
        async with async_session_factory() as session:
            scope_session_to_tenant(session, tenant.tenant_id)
            code = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
            await session.commit()
            return code

    codes = await asyncio.gather(*(allocate() for _ in range(10)))

    assert len(set(codes)) == 10
    year = current_year()
    assert sorted(codes) == [f"CAS-{year}-{str(n).zfill(6)}" for n in range(1, 11)]


async def test_allocation_rolls_back_with_its_transaction(
    tenant: TenantFixture,
) -> None:
    """O número volta atrás se a transação que o pediu não for adiante."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        await session.rollback()

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        code = await next_code(session, tenant_id=tenant.tenant_id, scope=CodeScope.CASE)
        await session.commit()

    assert code == f"CAS-{current_year()}-000001"
