"""Serviço do relato inicial (intake) de um caso — Fase 2, módulo intake.

Um caso tem no máximo um registro de intake (ver app/models/case_intake.py).
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
from app.models.case_intake import CaseIntake
from app.models.schemas.case_intake import CaseIntakeCreate, CaseIntakeUpdate

_MODEL_USED_MANUAL = "n/a"


async def _get_case_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case | None:
    return await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))


async def get_intake(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> CaseIntake | None:
    """Retorna o relato inicial de um caso do tenant autenticado, se existir.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.

    Returns:
        O relato inicial do caso, ou None se o caso ou o relato não existirem
        neste tenant.
    """
    return await session.scalar(
        select(CaseIntake).where(CaseIntake.tenant_id == tenant_id, CaseIntake.case_id == case_id)
    )


async def submit_intake(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: CaseIntakeCreate,
) -> CaseIntake | None:
    """Registra (ou substitui) o relato inicial de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso ao qual o relato pertence.
        actor_id: ID do usuário autenticado que está registrando o relato.
        payload: Relato inicial — texto livre e campos estruturados.

    Returns:
        Relato inicial criado ou atualizado, ou None se o caso não existir
        neste tenant.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None

    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    is_new = intake is None
    if intake is None:
        intake = CaseIntake(tenant_id=tenant_id, case_id=case_id, submitted_by=actor_id)
        session.add(intake)

    intake.narrative = payload.narrative
    intake.estimated_loss_amount = payload.estimated_loss_amount
    intake.incident_date = payload.incident_date
    intake.has_police_report = payload.has_police_report
    intake.claimed_documents = payload.claimed_documents
    intake.pending_information = payload.pending_information
    intake.metadata_ = payload.metadata
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="registrou relato inicial" if is_new else "atualizou relato inicial",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"case_intake_id": str(intake.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "case_intake", "case_id": str(case_id)},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(intake)
    return intake


async def update_intake(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: CaseIntakeUpdate,
) -> CaseIntake | None:
    """Atualiza parcialmente o relato inicial de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.
        actor_id: ID do usuário autenticado que está corrigindo o relato.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).

    Returns:
        Relato inicial atualizado, ou None se o caso ou o relato não
        existirem neste tenant.
    """
    started_at = time.monotonic()
    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    if intake is None:
        return None

    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        column = "metadata_" if field == "metadata" else field
        setattr(intake, column, value)

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="corrigiu relato inicial",
        module="intake",
        input_data=updates,
        output_data={"case_intake_id": str(intake.id)},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "case_intake", "case_id": str(case_id)},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(intake)
    return intake
