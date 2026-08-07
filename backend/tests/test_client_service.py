"""Testes do serviço de cadastro de clientes (app/services/client_service.py)."""

import uuid

from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.models.audit_log import AuditLog
from app.models.enums import AuditActor
from app.models.schemas.client import ClientCreate, ClientUpdate
from app.services.client_service import create_client, update_client
from tests.conftest import TenantFixture


async def test_create_client_persists_and_audits(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        client = await create_client(
            session,
            tenant_id=tenant.tenant_id,
            actor_id=tenant.user_id,
            payload=ClientCreate(full_name="Maria Souza", document_number="529.982.247-25"),
        )

        assert client.id is not None
        assert client.tenant_id == tenant.tenant_id
        assert client.full_name == "Maria Souza"
        assert client.code.startswith("CLI-")
        # Documento é normalizado para só dígitos na escrita (app/core/documents.py),
        # senão a checagem de duplicidade deixaria passar o mesmo CPF com máscara.
        assert client.document_number == "52998224725"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.tenant_id,
                AuditLog.action == "cadastrou cliente",
            )
        )
        assert audit is not None
        assert audit.actor == AuditActor.HUMAN
        assert audit.case_id is None
        # nenhum dado pessoal em claro deve sobreviver ao audit_log — apenas hashes.
        assert "Maria Souza" not in audit.input_hash
        assert "52998224725" not in audit.input_hash


async def test_update_client_changes_fields_and_audits(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        client = await create_client(
            session,
            tenant_id=tenant.tenant_id,
            actor_id=tenant.user_id,
            payload=ClientCreate(full_name="Cliente Original"),
        )

        updated = await update_client(
            session,
            tenant_id=tenant.tenant_id,
            actor_id=tenant.user_id,
            client_id=client.id,
            payload=ClientUpdate(full_name="Cliente Corrigido"),
        )

        assert updated is not None
        assert updated.full_name == "Cliente Corrigido"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.tenant_id,
                AuditLog.action == "atualizou cliente",
            )
        )
        assert audit is not None


async def test_update_client_returns_none_for_unknown_client(
    tenant: TenantFixture,
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        result = await update_client(
            session,
            tenant_id=tenant.tenant_id,
            actor_id=tenant.user_id,
            client_id=uuid.uuid4(),
            payload=ClientUpdate(full_name="Não existe"),
        )
        assert result is None


async def test_client_of_one_tenant_is_not_visible_to_another(
    tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        client = await create_client(
            session,
            tenant_id=tenant.tenant_id,
            actor_id=tenant.user_id,
            payload=ClientCreate(full_name="Cliente do Tenant A"),
        )
        client_id = client.id

        # create_client não commita (a transação pertence a quem chama), então
        # o cadastro precisa ser efetivado aqui para o outro tenant tentar lê-lo.
        await session.commit()

    # RLS (não apenas o filtro tenant_id em Python) bloqueia a leitura: mesmo
    # passando tenant_id=other_tenant.tenant_id ao serviço, a sessão do banco
    # está escopada para other_tenant via app.current_tenant.
    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        result = await update_client(
            session,
            tenant_id=other_tenant.tenant_id,
            actor_id=other_tenant.user_id,
            client_id=client_id,
            payload=ClientUpdate(full_name="Tentativa de sequestro"),
        )
        assert result is None
