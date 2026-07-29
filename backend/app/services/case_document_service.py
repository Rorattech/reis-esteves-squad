"""Serviço do checklist de documentos de um caso — Fase 2, módulo intake.

Toda função valida que o caso pertence ao tenant informado antes de ler ou
escrever (CLAUDE.md, seção 7) e grava uma entrada em audit_logs antes de
retornar (CLAUDE.md, seção 10).
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.models.case import Case
from app.models.case_document import CaseDocument
from app.models.schemas.case_document import CaseDocumentCreate, CaseDocumentUpdate

_MODEL_USED_MANUAL = "n/a"


async def _get_case_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case | None:
    return await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))


async def list_checklist(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> list[CaseDocument]:
    """Lista o checklist de documentos de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.

    Returns:
        Itens do checklist, mais recentes primeiro.
    """
    items = await session.scalars(
        select(CaseDocument)
        .where(CaseDocument.tenant_id == tenant_id, CaseDocument.case_id == case_id)
        .order_by(CaseDocument.created_at.desc())
    )
    return list(items.all())


async def add_checklist_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: CaseDocumentCreate,
) -> CaseDocument | None:
    """Adiciona um item ao checklist de documentos de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.
        actor_id: ID do usuário autenticado que está adicionando o item.
        payload: Nome, status inicial e origem do item.

    Returns:
        Item criado, ou None se o caso não existir neste tenant.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None

    item = CaseDocument(
        tenant_id=tenant_id,
        case_id=case_id,
        name=payload.name,
        status=payload.status,
        origin=payload.origin,
        notes=payload.notes,
    )
    session.add(item)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="adicionou item ao checklist de documentos",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"case_document_id": str(item.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "case_document", "case_id": str(case_id)},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(item)
    return item


async def update_checklist_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: CaseDocumentUpdate,
) -> CaseDocument | None:
    """Atualiza o status/observações de um item do checklist de documentos.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.
        document_id: ID do item do checklist.
        actor_id: ID do usuário autenticado que está atualizando o item.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).

    Returns:
        Item atualizado, ou None se o caso ou o item não existirem neste tenant.
    """
    started_at = time.monotonic()
    item = await session.scalar(
        select(CaseDocument).where(
            CaseDocument.tenant_id == tenant_id,
            CaseDocument.case_id == case_id,
            CaseDocument.id == document_id,
        )
    )
    if item is None:
        return None

    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="atualizou item do checklist de documentos",
        module="intake",
        input_data=updates,
        output_data={"case_document_id": str(item.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "case_document", "case_id": str(case_id)},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(item)
    return item
