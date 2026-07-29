"""Serviço de cadastro de clientes (partes lesadas) — Fase 2, Intake.

Toda função aqui recebe tenant_id explícito (nunca inferido do payload) e
grava uma entrada em audit_logs antes de retornar (CLAUDE.md, seções 7 e 10).
Não há chamada a modelo de IA nesta camada — model_used="n/a" é o valor
convencionado no projeto para ações puramente humanas (ver backend/tests/test_audit.py).
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.models.client import Client
from app.models.schemas.client import ClientCreate, ClientUpdate

_MODEL_USED_MANUAL = "n/a"


async def create_client(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: ClientCreate,
) -> Client:
    """Cadastra um novo cliente para o tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        payload: Dados do cliente.

    Returns:
        Cliente recém-criado.
    """
    started_at = time.monotonic()
    client = Client(
        tenant_id=tenant_id,
        full_name=payload.full_name,
        document_number=payload.document_number,
        email=payload.email,
        phone=payload.phone,
    )
    session.add(client)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="cadastrou cliente",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"client_id": str(client.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "client", "client_id": str(client.id)},
    )
    # case_id=None: o cliente ainda não pertence a nenhum caso no momento do
    # cadastro (audit_logs.case_id é opcional — ver app/models/audit_log.py).
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))

    await session.commit()
    await session.refresh(client)
    return client


async def update_client(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    client_id: uuid.UUID,
    payload: ClientUpdate,
) -> Client | None:
    """Atualiza campos de um cliente existente do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        client_id: ID do cliente a atualizar.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).

    Returns:
        Cliente atualizado, ou None se não existir neste tenant.
    """
    started_at = time.monotonic()
    client = await session.scalar(
        select(Client).where(Client.tenant_id == tenant_id, Client.id == client_id)
    )
    if client is None:
        return None

    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="atualizou cliente",
        module="intake",
        input_data=updates,
        output_data={"client_id": str(client.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "client", "client_id": str(client.id)},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))

    await session.commit()
    await session.refresh(client)
    return client
