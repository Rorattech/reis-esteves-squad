"""Orquestra a execução e a revisão humana do módulo Evidence (Fase 3.3).

Camada fina entre a API HTTP (`app/api/v1/evidence.py`) e o grafo LangGraph
(`orchestrator/graphs/evidence.py`): carrega as evidências e textos extraídos
já persistidos (Fases 3.1/3.2), monta o `CaseState`, invoca o grafo e
persiste o resultado — achados, checkpoint e audit_trail — numa única
transação.

O caso só avança para o módulo research por revisão humana explícita
(`review_evidence_findings`) — nunca automaticamente (CLAUDE.md, seção 2).
"""

import time
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.models.case import Case
from app.models.enums import CaseStatus, ExtractionOutcome, ModuleName
from app.models.evidence_file import EvidenceFile
from app.models.evidence_finding import EvidenceFindingRecord
from app.models.schemas.evidence_analysis import EvidenceReviewDecision, EvidenceReviewRequest
from app.services.case_intake_service import get_intake
from orchestrator.checkpoints import load_latest_checkpoint, save_checkpoint
from orchestrator.graphs.evidence import EvidenceContext, build_evidence_graph
from orchestrator.llm import LLMClient
from orchestrator.state import CaseState, EvidenceRecord

_MODEL_USED_MANUAL = "n/a"


class EvidenceNotReadyError(Exception):
    """Levantada quando o módulo Evidence não pode rodar ainda — ex.: intake
    não aprovado ou nenhuma evidência anexada."""


class EvidenceReviewConflictError(Exception):
    """Levantada quando não há análise de evidências pendente de revisão."""


async def _get_case_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case | None:
    return await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))


async def _load_evidence_records(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> list[EvidenceRecord]:
    """Monta os EvidenceRecord do caso: arquivo + extração bem-sucedida mais recente."""
    files = await session.scalars(
        select(EvidenceFile)
        .options(selectinload(EvidenceFile.extractions))
        .where(EvidenceFile.tenant_id == tenant_id, EvidenceFile.case_id == case_id)
        .order_by(EvidenceFile.created_at)
    )
    records: list[EvidenceRecord] = []
    for evidence in files.all():
        latest_success = next(
            (
                extraction
                for extraction in sorted(
                    evidence.extractions, key=lambda extraction: extraction.created_at, reverse=True
                )
                if extraction.outcome == ExtractionOutcome.SUCCEEDED
            ),
            None,
        )
        records.append(
            EvidenceRecord(
                evidence_id=str(evidence.id),
                filename=evidence.original_filename,
                mime_type=evidence.mime_type,
                processing_status=evidence.status.value,
                extracted_text=latest_success.extracted_text if latest_success else None,
                extraction_confidence=latest_success.confidence if latest_success else None,
                extraction_limitations=latest_success.limitations if latest_success else None,
            )
        )
    return records


def _build_initial_state(
    *,
    case: Case,
    tenant_id: uuid.UUID,
    narrative: str,
    records: list[EvidenceRecord],
) -> CaseState:
    """Monta o CaseState do módulo Evidence a partir do que já foi persistido.

    Cada execução é uma nova análise (não uma continuação): os campos de
    aprovação humana começam neutros até os nós do grafo os definirem.
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
        evidence_records=records,
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
        current_module="evidence",
        status="active",
    )


async def _persist_findings(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, state: CaseState
) -> None:
    """Substitui os achados pendentes do caso pelos da execução mais recente.

    Re-executar o módulo é uma nova recomendação — achados antigos ainda
    DRAFT_PENDING_REVIEW são removidos; o histórico permanece em audit_logs
    e nos checkpoints do CaseState.
    """
    await session.execute(
        delete(EvidenceFindingRecord).where(
            EvidenceFindingRecord.tenant_id == tenant_id,
            EvidenceFindingRecord.case_id == case_id,
            EvidenceFindingRecord.status == "DRAFT_PENDING_REVIEW",
        )
    )
    for finding in state["evidence_findings"]:
        session.add(
            EvidenceFindingRecord(
                id=uuid.UUID(finding.finding_id),
                tenant_id=tenant_id,
                case_id=case_id,
                evidence_id=(
                    uuid.UUID(finding.source_evidence_id)
                    if finding.source_evidence_id
                    else None
                ),
                agent=finding.agent,
                category=finding.category,
                evidence_type=finding.evidence_type,
                summary=finding.summary,
                relevance=finding.relevance,
                suggested_use=finding.suggested_use,
                gaps=finding.gaps,
                confidence=finding.confidence,
                status=finding.status,
            )
        )


async def run_evidence(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, llm_client: LLMClient
) -> tuple[Case, CaseState] | None:
    """Executa o grafo do módulo Evidence (documental + specialist) para um caso.

    Persiste os achados em `evidence_findings`, salva um checkpoint do
    CaseState e grava cada entrada do audit_trail em audit_logs — tudo na
    mesma transação (CLAUDE.md, seção 10). O caso termina PENDING_APPROVAL:
    só avança para research via `review_evidence_findings`.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso a analisar.
        llm_client: Provedor de IA (nunca chamado fora de um nó do grafo).

    Returns:
        Tupla (Case atualizado, CaseState final), ou None se o caso não
        existir neste tenant.

    Raises:
        EvidenceNotReadyError: Se o caso ainda não passou pela revisão do
            Intake (current_module != evidence) ou não tem evidência anexada.
        orchestrator.graphs.evidence.EvidenceGraphValidationError: Se o
            CaseState montado for inválido.
        orchestrator.graphs.evidence.EvidenceTraceabilityError: Se o modelo
            produzir achado sem vínculo com evidência original.
        orchestrator.llm.LLMNotConfiguredError: Se nenhum LLMClient estiver
            configurado.
        orchestrator.graphs.evidence.LLMOutputValidationError: Se a saída do
            modelo não validar contra o schema esperado.
    """
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    if case.current_module != ModuleName.EVIDENCE:
        raise EvidenceNotReadyError(
            "O caso ainda não está no módulo de evidências — a triagem do "
            "Intake precisa ser aprovada por um advogado antes "
            "(POST .../intake/review)."
        )

    records = await _load_evidence_records(session, tenant_id=tenant_id, case_id=case_id)
    if not records:
        raise EvidenceNotReadyError(
            "Nenhuma evidência anexada ao caso — envie ao menos um arquivo "
            "(POST .../evidence) antes de rodar a análise."
        )

    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    narrative = intake.narrative if intake is not None else ""

    state = _build_initial_state(
        case=case, tenant_id=tenant_id, narrative=narrative, records=records
    )

    graph = build_evidence_graph()
    result = await graph.ainvoke(state, context=EvidenceContext(llm_client=llm_client))

    case.human_review_required = True
    case.status = CaseStatus.PENDING_APPROVAL

    await _persist_findings(session, tenant_id=tenant_id, case_id=case_id, state=result)
    await save_checkpoint(session, result)
    for entry in result["audit_trail"]:
        session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))
    await session.commit()

    return case, result


async def get_evidence_analysis(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> tuple[Case, CaseState, list[EvidenceFindingRecord]] | None:
    """Carrega o resultado mais recente do módulo Evidence para um caso.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.

    Returns:
        Tupla (Case, CaseState do checkpoint mais recente, achados
        persistidos), ou None se o caso não existir. O CaseState pode ser de
        outro módulo se o Evidence ainda não rodou — o chamador decide pelo
        campo `evidence_outcome`.
    """
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    state = await load_latest_checkpoint(session, tenant_id=tenant_id, case_id=case_id)
    findings = await session.scalars(
        select(EvidenceFindingRecord)
        .where(
            EvidenceFindingRecord.tenant_id == tenant_id,
            EvidenceFindingRecord.case_id == case_id,
        )
        .order_by(EvidenceFindingRecord.created_at)
    )
    return case, (state or {}), list(findings.all())


async def review_evidence_findings(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: EvidenceReviewRequest,
) -> Case | None:
    """Registra a decisão humana sobre o inventário probatório do caso.

    "approve" marca os achados como APPROVED e avança o caso para o módulo
    research; "return_for_information" mantém o caso em evidence, aguardando
    novas evidências/reprocessamento. Nunca aprova nada sozinha (CLAUDE.md,
    seção 2).

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso sendo revisado.
        actor_id: Usuário autenticado que está revisando.
        payload: Decisão e justificativa.

    Returns:
        O Case atualizado, ou None se não existir neste tenant.

    Raises:
        EvidenceReviewConflictError: Se o caso não estiver com uma análise de
            evidências pendente de revisão.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    if case.current_module != ModuleName.EVIDENCE or case.status != CaseStatus.PENDING_APPROVAL:
        raise EvidenceReviewConflictError(
            "Este caso não tem nenhuma análise de evidências pendente de revisão."
        )

    findings = list(
        (
            await session.scalars(
                select(EvidenceFindingRecord).where(
                    EvidenceFindingRecord.tenant_id == tenant_id,
                    EvidenceFindingRecord.case_id == case_id,
                    EvidenceFindingRecord.status == "DRAFT_PENDING_REVIEW",
                )
            )
        ).all()
    )

    before: dict[str, Any] = {
        "status": case.status.value,
        "current_module": case.current_module.value,
        "pending_findings": len(findings),
    }

    if payload.decision == EvidenceReviewDecision.APPROVE:
        for finding in findings:
            finding.status = "APPROVED"
        case.human_review_required = False
        case.status = CaseStatus.IN_PROGRESS
        case.current_module = ModuleName.RESEARCH
    else:
        # RETURN_FOR_INFORMATION: caso continua em evidence, pendente — a
        # próxima ação humana é anexar/reprocessar evidências e rodar de novo.
        case.human_review_required = True
        case.status = CaseStatus.IN_PROGRESS

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action=f"revisão humana das evidências: {payload.decision.value}",
        module="evidence",
        input_data={"decision": payload.decision.value, "before": before},
        output_data={
            "status": case.status.value,
            "current_module": case.current_module.value,
            "human_review_required": case.human_review_required,
        },
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        # Justificativa do advogado em claro — visível no histórico do caso.
        metadata={"decision": payload.decision.value, "notes": payload.notes},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))

    await session.commit()
    await session.refresh(case)
    return case
