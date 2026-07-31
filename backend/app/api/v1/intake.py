"""Rotas de Intake e revisão humana (Fase 2.4 — CLAUDE.md, seção 7).

Todas as rotas exigem TenantMiddleware (JWT válido) e usam a sessão já
escopada por tenant injetada em request.state.db via get_tenant_session —
nunca abrem uma sessão própria nem aceitam tenant_id/user_id vindos do
payload do cliente (mesmo padrão de app/api/v1/cases.py).

Nenhuma rota aqui aprova uma estratégia ou peça jurídica automaticamente
(CLAUDE.md, seção 2) — "approve"/"correct" no endpoint de revisão só fazem o
caso avançar do módulo intake para evidence, e sempre a partir de uma ação
humana explícita e autenticada.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.core.rbac import require_role
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.case_document import CaseDocument
from app.models.case_intake import CaseIntake
from app.models.enums import UserRole
from app.models.schemas.case import CaseResponse
from app.models.schemas.case_document import (
    CaseDocumentCreate,
    CaseDocumentResponse,
    CaseDocumentUpdate,
)
from app.models.schemas.case_intake import CaseIntakeCreate, CaseIntakeResponse, CaseIntakeUpdate
from app.models.schemas.intake import (
    AuditLogEntryResponse,
    CaseStageAdvanceRequest,
    IntakeResultResponse,
    IntakeReviewRequest,
)
from app.services.case_document_service import (
    add_checklist_item,
    list_checklist,
    update_checklist_item,
)
from app.services.case_intake_service import get_intake, submit_intake, update_intake
from app.services.intake_orchestration_service import (
    IntakeNotReadyError,
    IntakeReviewConflictError,
    StageAdvanceConflictError,
    advance_case_to_evidence,
    review_intake_recommendation,
    run_intake,
)
from orchestrator.checkpoints import load_latest_checkpoint
from orchestrator.graphs.intake import IntakeValidationError, LLMOutputValidationError
from orchestrator.llm import LLMClient, LLMNotConfiguredError
from orchestrator.state import CaseState

logger = structlog.get_logger()

router = APIRouter(prefix="/cases/{case_id}", tags=["intake"])

# viewer só lê; escrever/rodar/revisar o intake exige um papel operacional
# (CLAUDE.md, seção 12) — mesmo conjunto de papéis usado em app/api/v1/cases.py.
_require_case_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)
# Histórico de auditoria é mais sensível que os dados do caso em si (nomes de
# modelo, hashes, metadados técnicos) — não exposto a viewer.
_require_audit_reader = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)


async def get_llm_client() -> LLMClient:
    """Fornece o LLMClient real usado por `POST .../intake/run`.

    Nenhum provedor de IA está configurado neste projeto ainda — nenhuma
    credencial existe em .env, e nenhuma implementação concreta de
    `orchestrator.llm.LLMClient` foi criada (CLAUDE.md, seção 15: nunca
    chamar um provedor fora de um nó do grafo). Por isso esta dependency
    sempre falha de forma explícita, em vez de fingir sucesso ou inventar
    uma classificação.

    Testes de API sobrescrevem esta dependency via
    `app.dependency_overrides[get_llm_client]` para injetar um stub.

    Raises:
        HTTPException: 503, sempre, até uma implementação real existir.
    """
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Provedor de IA ainda não configurado neste ambiente.",
    )


async def _get_case_or_404(session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID) -> Case:
    case = await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    return case


def _build_result_response(case: Case, state: CaseState) -> IntakeResultResponse:
    """Combina o `Case` persistido (fonte de verdade de status/current_module)
    com o `CaseState` do checkpoint (única fonte de intake_outcome/
    missing_information/out_of_scope_reason/documents_requested — campos que
    não têm coluna própria em `cases`)."""
    return IntakeResultResponse(
        case_id=case.id,
        intake_outcome=state.get("intake_outcome"),
        platform=case.platform,
        fraud_type=case.fraud_type,
        urgency=case.urgency,
        area=case.area,
        matter=case.matter,
        documents_requested=state.get("documents_requested", []),
        missing_information=state.get("missing_information", []),
        out_of_scope_reason=state.get("out_of_scope_reason"),
        human_review_required=case.human_review_required,
        status=case.status,
        current_module=case.current_module,
    )


# --- Relato inicial (CaseIntake) --------------------------------------------


@router.post(
    "/intake",
    response_model=CaseIntakeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_case_writer)],
)
async def submit_case_intake(
    case_id: uuid.UUID,
    payload: CaseIntakeCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> CaseIntake:
    """Registra o relato inicial (texto livre + campos estruturados) de um caso.

    Idempotente por caso: reenviar substitui o relato anterior (ver
    `app.services.case_intake_service.submit_intake`).

    Args:
        case_id: ID do caso.
        payload: Relato inicial — narrativa e campos estruturados.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O relato inicial criado ou atualizado.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    intake = await submit_intake(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=uuid.UUID(request.state.user_id),
        payload=payload,
    )
    if intake is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    logger.info("intake.narrative.submit", case_id=str(case_id), tenant_id=str(tenant_id))
    return intake


@router.get("/intake", response_model=CaseIntakeResponse)
async def get_case_intake(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> CaseIntake:
    """Retorna o relato inicial de um caso do tenant autenticado.

    Args:
        case_id: ID do caso.
        request: Request HTTP corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O relato inicial do caso.

    Raises:
        HTTPException: 404 se o caso não existir, ou se ainda não houver
            relato inicial registrado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _get_case_or_404(session, tenant_id, case_id)
    intake = await get_intake(session, tenant_id=tenant_id, case_id=case_id)
    if intake is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Relato inicial ainda não foi registrado para este caso.",
        )
    return intake


@router.patch(
    "/intake",
    response_model=CaseIntakeResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def update_case_intake(
    case_id: uuid.UUID,
    payload: CaseIntakeUpdate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> CaseIntake:
    """Corrige campos do relato inicial de um caso — todos opcionais (semântica PATCH).

    Args:
        case_id: ID do caso.
        payload: Campos a corrigir.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O relato inicial atualizado.

    Raises:
        HTTPException: 404 se o caso não existir, ou se ainda não houver
            relato inicial registrado para corrigir.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    intake = await update_intake(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=uuid.UUID(request.state.user_id),
        payload=payload,
    )
    if intake is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Caso ou relato inicial não encontrado."
        )
    logger.info("intake.narrative.update", case_id=str(case_id), tenant_id=str(tenant_id))
    return intake


# --- Checklist de documentos (CaseDocument) ----------------------------------


@router.post(
    "/documents",
    response_model=CaseDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_case_writer)],
)
async def add_case_document(
    case_id: uuid.UUID,
    payload: CaseDocumentCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> CaseDocument:
    """Adiciona um item ao checklist de documentos de um caso.

    Args:
        case_id: ID do caso.
        payload: Nome, status inicial e origem do item.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O item de checklist criado.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    item = await add_checklist_item(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=uuid.UUID(request.state.user_id),
        payload=payload,
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    logger.info("intake.documents.add", case_id=str(case_id), tenant_id=str(tenant_id))
    return item


@router.get("/documents", response_model=list[CaseDocumentResponse])
async def list_case_documents(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[CaseDocument]:
    """Lista o checklist de documentos de um caso do tenant autenticado.

    Args:
        case_id: ID do caso.
        request: Request HTTP corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Itens do checklist (lista vazia se nenhum item existir ainda).

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _get_case_or_404(session, tenant_id, case_id)
    return await list_checklist(session, tenant_id=tenant_id, case_id=case_id)


@router.patch(
    "/documents/{document_id}",
    response_model=CaseDocumentResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def update_case_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: CaseDocumentUpdate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> CaseDocument:
    """Atualiza status/observações de um item do checklist de documentos.

    Args:
        case_id: ID do caso.
        document_id: ID do item do checklist.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O item de checklist atualizado.

    Raises:
        HTTPException: 404 se o caso ou o item não existirem neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    item = await update_checklist_item(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        document_id=document_id,
        actor_id=uuid.UUID(request.state.user_id),
        payload=payload,
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    logger.info("intake.documents.update", case_id=str(case_id), tenant_id=str(tenant_id))
    return item


# --- Execução e resultado do Intake (coordinator + triage) -------------------


@router.post(
    "/intake/run",
    response_model=IntakeResultResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def run_case_intake(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    llm_client: LLMClient = Depends(get_llm_client),
) -> IntakeResultResponse:
    """Executa coordinator + triage (orchestrator/graphs/intake.py) para um caso.

    O resultado é sempre uma recomendação (CLAUDE.md, seção 2) — nunca uma
    decisão final: o caso fica marcado como aguardando revisão humana (ver
    `POST .../intake/review`).

    Args:
        case_id: ID do caso a classificar.
        request: Request HTTP corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.
        llm_client: Provedor de IA (injetado via `get_llm_client`).

    Returns:
        O resultado da classificação/triagem mais recente.

    Raises:
        HTTPException: 404 se o caso não existir; 422 se o caso ainda não
            tiver relato inicial ou se o CaseState resultante for inválido;
            503 se nenhum provedor de IA estiver configurado; 502 se a saída
            do modelo não validar contra o schema esperado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        outcome = await run_intake(
            session, tenant_id=tenant_id, case_id=case_id, llm_client=llm_client
        )
    except IntakeNotReadyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except IntakeValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LLMOutputValidationError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="O modelo de IA retornou uma saída inválida."
        ) from exc
    if outcome is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    case, state = outcome
    logger.info(
        "intake.run",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        outcome=state["intake_outcome"],
    )
    return _build_result_response(case, state)


@router.get("/intake/result", response_model=IntakeResultResponse)
async def get_case_intake_result(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> IntakeResultResponse:
    """Consulta o resultado mais recente de coordinator/triage para um caso.

    Args:
        case_id: ID do caso.
        request: Request HTTP corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O resultado da classificação/triagem mais recente.

    Raises:
        HTTPException: 404 se o caso não existir, ou se o Intake ainda não
            tiver sido executado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    case = await _get_case_or_404(session, tenant_id, case_id)
    state = await load_latest_checkpoint(session, tenant_id=tenant_id, case_id=case_id)
    if state is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="O Intake ainda não foi executado para este caso."
        )
    return _build_result_response(case, state)


# --- Revisão humana -----------------------------------------------------------


@router.post(
    "/intake/review",
    response_model=CaseResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def review_case_intake(
    case_id: uuid.UUID,
    payload: IntakeReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Case:
    """Registra a decisão humana sobre a recomendação de coordinator/triage.

    "approve"/"correct" fazem o caso avançar do módulo intake para evidence;
    "return_for_information" mantém o caso em intake, aguardando
    complementação. Nunca aprova nada sozinha (CLAUDE.md, seção 2) — só
    executa a decisão explícita informada no payload.

    Args:
        case_id: ID do caso.
        payload: Decisão (approve/correct/return_for_information),
            justificativa (obrigatória fora de "approve") e campos
            corrigidos quando a decisão for "correct".
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O caso atualizado.

    Raises:
        HTTPException: 404 se o caso não existir; 409 se não houver nenhuma
            recomendação pendente de revisão.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        case = await review_intake_recommendation(
            session,
            tenant_id=tenant_id,
            case_id=case_id,
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except IntakeReviewConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    logger.info(
        "intake.review",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        decision=payload.decision.value,
    )
    return case


@router.post(
    "/intake/advance",
    response_model=CaseResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def advance_case_stage(
    case_id: uuid.UUID,
    payload: CaseStageAdvanceRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Case:
    """Conclui a abertura do caso e o avança para o módulo de evidências.

    Existe para o caso — comum neste ambiente — em que nenhuma recomendação
    de triagem foi produzida e portanto não há nada a aprovar em
    `POST .../intake/review`: sem esta rota o caso ficaria preso na abertura
    indefinidamente, para qualquer papel. Nunca avança sozinha (CLAUDE.md,
    seção 2) — depende de uma ação humana explícita e autenticada, registrada
    em audit_logs.

    Args:
        case_id: ID do caso.
        payload: Justificativa opcional do avanço.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O caso atualizado, já no módulo de evidências.

    Raises:
        HTTPException: 404 se o caso não existir; 409 se o caso já tiver
            saído da abertura; 422 se ainda não houver relato inicial.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        case = await advance_case_to_evidence(
            session,
            tenant_id=tenant_id,
            case_id=case_id,
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except StageAdvanceConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntakeNotReadyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    logger.info("intake.advance", case_id=str(case_id), tenant_id=str(tenant_id))
    return case


# --- Histórico de auditoria ---------------------------------------------------


@router.get(
    "/audit-log",
    response_model=list[AuditLogEntryResponse],
    dependencies=[Depends(_require_audit_reader)],
)
async def get_case_audit_log(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[AuditLog]:
    """Lista o histórico de auditoria de um caso, do mais antigo ao mais recente.

    Restrito a admin/lawyer/paralegal (CLAUDE.md, seção 12) — mais sensível
    que os dados do caso em si (nomes de modelo, hashes, metadados técnicos).

    Args:
        case_id: ID do caso.
        request: Request HTTP corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Entradas de audit_logs do caso.

    Raises:
        HTTPException: 403 se o usuário autenticado for viewer; 404 se o
            caso não existir neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _get_case_or_404(session, tenant_id, case_id)
    logs = await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at)
    )
    return list(logs.all())
