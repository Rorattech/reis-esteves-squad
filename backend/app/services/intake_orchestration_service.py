"""Orquestra a execução e a revisão humana do módulo Intake (Fase 2.4).

Camada fina entre a API HTTP (`app/api/v1/intake.py`) e o grafo LangGraph
(`orchestrator/graphs/intake.py`): monta o `CaseState` inicial a partir do
`Case`/`CaseIntake` já persistidos, invoca o grafo, e persiste o resultado —
`Case`, checkpoint e audit_trail — numa única transação.

Toda função aqui recebe tenant_id explícito e nunca retorna/edita um caso de
outro tenant (CLAUDE.md, seção 7).
"""

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.models.case import Case
from app.models.enums import CaseStatus, ModuleName
from app.models.schemas.intake import (
    CaseStageAdvanceRequest,
    IntakeReviewDecision,
    IntakeReviewRequest,
)
from app.services.case_intake_service import get_intake
from orchestrator.checkpoints import save_checkpoint
from orchestrator.graphs.intake import (
    IntakeContext,
    build_intake_graph,
    persist_intake_recommendation,
)
from orchestrator.llm import LLMClient
from orchestrator.state import CaseState

_MODEL_USED_MANUAL = "n/a"


class IntakeNotReadyError(Exception):
    """Levantada quando o Intake não pode rodar ainda — ex.: sem relato inicial registrado."""


class IntakeReviewConflictError(Exception):
    """Levantada quando não há recomendação pendente de revisão para o caso."""


class StageAdvanceConflictError(Exception):
    """Levantada quando o caso não está no módulo intake e portanto não tem o que avançar."""


async def _get_case_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case | None:
    return await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))


def _build_initial_state(*, case: Case, tenant_id: uuid.UUID, narrative: str) -> CaseState:
    """Monta o CaseState inicial a partir do Case/CaseIntake já persistidos.

    A cada execução o estado é reconstruído do zero (não do último
    checkpoint): rodar o Intake de novo é sempre uma nova classificação, não
    uma continuação — os campos de aprovação humana sempre começam neutros
    até os nós do grafo os definirem (ver orchestrator/graphs/intake.py).
    """
    return CaseState(
        case_id=str(case.id),
        tenant_id=str(tenant_id),
        narrative=narrative,
        platform=case.platform,
        fraud_type=case.fraud_type.value,
        urgency=case.urgency.value,
        area=case.area.value if case.area else None,
        matter=case.matter,
        intake_outcome=None,
        missing_information=[],
        out_of_scope_reason=None,
        documents_requested=[],
        evidence_records=[],
        evidence_inventory=[],
        evidence_findings=[],
        specialist_assessment=None,
        evidence_outcome=None,
        legal_sources=[],
        strategy_memo=None,
        draft_petition=None,
        human_approval_required=False,
        human_approval_status="na",
        approved_by=None,
        approved_at=None,
        audit_trail=[],
        current_module=case.current_module.value,
        status="active",
    )


async def run_intake(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, llm_client: LLMClient
) -> tuple[Case, CaseState] | None:
    """Executa o grafo do módulo Intake (coordinator + triage) para um caso.

    Persiste o resultado no `Case`, salva um checkpoint do `CaseState` e
    grava cada entrada do `audit_trail` em `audit_logs` — tudo na mesma
    transação (CLAUDE.md, seção 10).

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso a classificar.
        llm_client: Provedor de IA já configurado (nunca chamado fora daqui
            ou de um nó do grafo — CLAUDE.md, seção 15).

    Returns:
        Tupla (`Case` atualizado, `CaseState` final após coordinator/triage),
        ou None se o caso não existir neste tenant. `Case.status`/`area`/
        `matter`/etc. já refletem `persist_intake_recommendation`; campos que
        não têm coluna própria (`intake_outcome`, `missing_information`,
        `out_of_scope_reason`, `documents_requested`) só existem no `CaseState`.

    Raises:
        IntakeNotReadyError: Se o caso ainda não tiver um relato inicial
            (`CaseIntake`) registrado — o grafo nunca inventa uma narrativa.
        orchestrator.graphs.intake.IntakeValidationError: Se o CaseState
            montado não tiver os campos mínimos (não deveria ocorrer para um
            caso e narrativa válidos — falha explícita mesmo assim).
        orchestrator.llm.LLMNotConfiguredError: Se nenhum LLMClient estiver
            configurado neste ambiente.
        orchestrator.graphs.intake.LLMOutputValidationError: Se a saída do
            modelo não validar contra o schema esperado.
    """
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None

    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    if intake is None:
        raise IntakeNotReadyError(
            "O caso ainda não tem relato inicial registrado — "
            "envie o relato (POST .../intake) antes de rodar a triagem."
        )

    state = _build_initial_state(case=case, tenant_id=tenant_id, narrative=intake.narrative)

    graph = build_intake_graph()
    result = await graph.ainvoke(state, context=IntakeContext(llm_client=llm_client))

    # persist_intake_recommendation busca o Case de novo, mas dentro da MESMA
    # sessão — o identity map do SQLAlchemy garante que é a mesma instância
    # `case` acima, já mutada em memória (sem precisar de session.refresh).
    await persist_intake_recommendation(session, result)
    await save_checkpoint(session, result)
    for entry in result["audit_trail"]:
        session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))
    await session.commit()

    return case, result


async def review_intake_recommendation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: IntakeReviewRequest,
) -> Case | None:
    """Registra a decisão humana (aprovar/corrigir/devolver) sobre a recomendação do Intake.

    Nunca aprova nada sozinha: só é chamada a partir de uma ação explícita de
    um usuário autenticado (CLAUDE.md, seção 2). "approve" e "correct" fazem
    o caso avançar para o módulo `evidence`; "return_for_information"
    mantém o caso em `intake`, aguardando complementação.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso sendo revisado.
        actor_id: ID do usuário autenticado que está revisando.
        payload: Decisão, justificativa e (opcional) campos corrigidos.

    Returns:
        O `Case` atualizado, ou None se não existir neste tenant.

    Raises:
        IntakeReviewConflictError: Se o caso não estiver com uma recomendação
            de Intake pendente de revisão (`status == PENDING_APPROVAL`,
            só atingido quando `intake_outcome == "awaiting_human_review"`
            — ver `orchestrator/graphs/intake.py::persist_intake_recommendation`).
            Um caso "blocked"/"awaiting_information" ou recém-criado (nunca
            executado) não tem uma recomendação estruturada para
            aprovar/corrigir — o caminho correto nesses casos é completar o
            relato/checklist e rodar o Intake novamente.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    if case.status != CaseStatus.PENDING_APPROVAL:
        raise IntakeReviewConflictError(
            "Este caso não tem nenhuma recomendação de Intake pendente de revisão."
        )

    before = _case_classification_snapshot(case)

    if payload.decision == IntakeReviewDecision.CORRECT:
        if payload.platform is not None:
            case.platform = payload.platform
        if payload.fraud_type is not None:
            case.fraud_type = payload.fraud_type
        if payload.urgency is not None:
            case.urgency = payload.urgency
        if payload.area is not None:
            case.area = payload.area
        if payload.matter is not None:
            case.matter = payload.matter

    if payload.decision in (IntakeReviewDecision.APPROVE, IntakeReviewDecision.CORRECT):
        case.human_review_required = False
        case.status = CaseStatus.IN_PROGRESS
        case.current_module = ModuleName.EVIDENCE
    else:
        # RETURN_FOR_INFORMATION: caso continua em intake, ainda pendente de
        # revisão — a próxima ação humana é complementar o relato/checklist.
        case.human_review_required = True
        case.status = CaseStatus.IN_PROGRESS

    after = _case_classification_snapshot(case)

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action=f"revisão humana do intake: {payload.decision.value}",
        module="intake",
        input_data={"decision": payload.decision.value, "before": before},
        output_data=after,
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        # decision/notes ficam em claro no metadata (não hasheados) — é a
        # justificativa do advogado, precisa ficar visível no histórico do
        # caso (docs/roadmap_mvp_squad_digital.md, 2.6), nunca dado pessoal
        # do cliente.
        metadata={"decision": payload.decision.value, "notes": payload.notes},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(case)
    return case


async def advance_case_to_evidence(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: CaseStageAdvanceRequest,
) -> Case | None:
    """Avança o caso da abertura (módulo intake) para evidências por decisão humana.

    Caminho para os casos em que a triagem assistida por IA não produziu (ou
    não podia produzir) uma recomendação a revisar — por exemplo quando
    nenhum provedor de IA está configurado no ambiente, situação em que
    `POST .../intake/run` responde 503 e o caso jamais chega a
    `PENDING_APPROVAL`. Sem esta rota o caso ficaria preso em intake para
    sempre, inclusive para admin.

    Não é uma decisão automática nem uma aprovação de conteúdo jurídico
    (CLAUDE.md, seção 2): é o advogado assumindo explicitamente que a
    abertura do caso está completa. Fica registrado em audit_logs como ação
    humana, com `ai_triage_reviewed=False` para deixar claro no histórico que
    nenhuma recomendação de IA foi revisada aqui.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso a avançar.
        actor_id: ID do usuário autenticado que está avançando o caso.
        payload: Justificativa opcional do avanço.

    Returns:
        O `Case` atualizado, ou None se não existir neste tenant.

    Raises:
        StageAdvanceConflictError: Se o caso já tiver saído do módulo intake.
        IntakeNotReadyError: Se o caso ainda não tiver relato inicial — o
            módulo de evidências trabalha sobre o relato, então avançar sem
            ele deixaria a próxima etapa sem contexto nenhum.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    if case.current_module != ModuleName.INTAKE:
        raise StageAdvanceConflictError(
            "Este caso já saiu da abertura de caso — não há etapa de abertura a concluir."
        )

    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    if intake is None:
        raise IntakeNotReadyError(
            "Registre o relato inicial antes de avançar o caso para Evidências."
        )

    before = _case_classification_snapshot(case)

    case.current_module = ModuleName.EVIDENCE
    case.status = CaseStatus.IN_PROGRESS
    case.human_review_required = False

    after = _case_classification_snapshot(case)

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="avanço manual da abertura de caso para evidências",
        module="intake",
        input_data={"before": before},
        output_data=after,
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        # notes fica em claro (não hasheado), como na revisão da triagem: é a
        # justificativa do advogado e precisa ficar legível no histórico do
        # caso — nunca dado pessoal do cliente.
        metadata={"notes": payload.notes, "ai_triage_reviewed": False},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(case)
    return case


def _case_classification_snapshot(case: Case) -> dict[str, Any]:
    return {
        "platform": case.platform,
        "fraud_type": case.fraud_type.value,
        "urgency": case.urgency.value,
        "area": case.area.value if case.area else None,
        "matter": case.matter,
        "status": case.status.value,
        "current_module": case.current_module.value,
        "human_review_required": case.human_review_required,
    }
