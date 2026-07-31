"""Rotas de evidências de um caso (Fase 3.1 — CLAUDE.md, seções 7 e 12).

Todas as rotas exigem TenantMiddleware (JWT válido) e usam a sessão já
escopada por tenant injetada via get_tenant_session — mesmo padrão de
app/api/v1/cases.py e intake.py. O conteúdo original só sai pela rota
autenticada de download (FileResponse) — nunca existe URL pública ou
permanente para um arquivo de evidência.
"""

import uuid

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intake import get_llm_client
from app.core.config import settings
from app.core.db import get_tenant_session
from app.core.rbac import require_role
from app.core.storage import EvidenceStorage, EvidenceStorageError, get_evidence_storage
from app.models.enums import EvidenceProcessingStatus, UserRole
from app.models.evidence_file import EvidenceFile
from app.models.schemas.evidence_analysis import (
    EvidenceAnalysisResultResponse,
    EvidenceFindingResponse,
    EvidenceReviewRequest,
    SpecialistAssessmentResponse,
)
from app.models.schemas.evidence_extraction import (
    EvidenceExtractionResponse,
    ExtractionReviewCreate,
    ExtractionReviewResponse,
)
from app.models.schemas.evidence_file import EvidenceFileResponse
from app.services.evidence_orchestration_service import (
    EvidenceNotReadyError,
    EvidenceReviewConflictError,
    get_evidence_analysis,
    review_evidence_findings,
    run_evidence,
)
from app.services.evidence_service import (
    EvidenceValidationError,
    get_evidence,
    list_evidence,
    record_evidence_access,
    store_evidence,
)
from app.services.extraction_service import (
    list_extractions,
    process_evidence,
    review_extraction,
)
from orchestrator.graphs.evidence import (
    EvidenceGraphValidationError,
    EvidenceTraceabilityError,
    LLMOutputValidationError,
)
from orchestrator.llm import LLMClient, LLMNotConfiguredError
from orchestrator.state import CaseState

logger = structlog.get_logger()

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])

# viewer só lê o inventário; enviar arquivo exige papel operacional
# (CLAUDE.md, seção 12 — mesmo conjunto de app/api/v1/cases.py).
_require_evidence_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)
# Baixar o conteúdo original é mais sensível que ler metadados do
# inventário — viewer não acessa o arquivo em si.
_require_evidence_reader = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)


async def _get_evidence_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID, evidence_id: uuid.UUID
) -> EvidenceFile:
    evidence = await get_evidence(
        session, tenant_id=tenant_id, case_id=case_id, evidence_id=evidence_id
    )
    if evidence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Evidência não encontrada.")
    return evidence


@router.post(
    "",
    response_model=EvidenceFileResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_evidence_writer)],
)
async def upload_evidence(
    case_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    origin: str = Form("upload_portal"),
    session: AsyncSession = Depends(get_tenant_session),
    storage: EvidenceStorage = Depends(get_evidence_storage),
) -> EvidenceFile:
    """Anexa um arquivo de evidência a um caso do tenant autenticado.

    O original é preservado intacto (nunca sobrescrito), com hash SHA-256 de
    integridade e detecção de duplicidade por hash dentro do tenant. Upload,
    validação e resultado ficam registrados em audit_logs. Após o commit, o
    pipeline de extração (Fase 3.2) é disparado em background.

    Args:
        case_id: ID do caso.
        request: Request corrente, com `state.tenant_id`/`state.user_id`.
        background_tasks: Fila de tarefas pós-resposta (pipeline de extração).
        file: Arquivo enviado (multipart/form-data).
        origin: De onde a evidência veio (ex.: "upload_portal", "whatsapp").
        session: Sessão do banco já escopada por tenant.
        storage: Armazenamento privado de originais.

    Returns:
        Metadados da evidência criada (nunca a storage_key interna).

    Raises:
        HTTPException: 404 se o caso não existir neste tenant; 422 se o
            arquivo for inválido (tipo, tamanho ou conteúdo).
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    content = await file.read()
    try:
        evidence = await store_evidence(
            session,
            storage,
            tenant_id=tenant_id,
            case_id=case_id,
            actor_id=uuid.UUID(request.state.user_id),
            original_filename=file.filename or "sem_nome",
            mime_type=file.content_type or "application/octet-stream",
            content=content,
            origin=origin,
            max_upload_mb=settings.backend_max_upload_mb,
            client_host=request.client.host if request.client else None,
        )
    except EvidenceValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if evidence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    background_tasks.add_task(process_evidence, tenant_id, evidence.id, storage)
    logger.info(
        "evidence.upload",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        evidence_id=str(evidence.id),
        is_duplicate=evidence.duplicate_of_id is not None,
    )
    return evidence


@router.get("", response_model=list[EvidenceFileResponse])
async def list_case_evidence(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[EvidenceFile]:
    """Lista o inventário de evidências de um caso do tenant autenticado.

    Args:
        case_id: ID do caso.
        request: Request corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Evidências do caso, mais recentes primeiro.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    items = await list_evidence(session, tenant_id=tenant_id, case_id=case_id)
    if items is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    return items


@router.get("/{evidence_id}", response_model=EvidenceFileResponse)
async def get_case_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> EvidenceFile:
    """Retorna os metadados de uma evidência específica do tenant autenticado.

    Args:
        case_id: ID do caso.
        evidence_id: ID da evidência.
        request: Request corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Metadados da evidência.

    Raises:
        HTTPException: 404 se a evidência não existir neste tenant/caso.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    return await _get_evidence_or_404(session, tenant_id, case_id, evidence_id)


@router.get(
    "/{evidence_id}/download",
    dependencies=[Depends(_require_evidence_reader)],
)
async def download_case_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    storage: EvidenceStorage = Depends(get_evidence_storage),
) -> FileResponse:
    """Baixa o conteúdo original de uma evidência, com acesso auditado.

    Único caminho para o conteúdo do arquivo — sempre autenticado, sempre
    escopado por tenant, nunca via URL pública. Cada acesso gera entrada em
    audit_logs (cadeia de custódia — roadmap 3.1).

    Args:
        case_id: ID do caso.
        evidence_id: ID da evidência.
        request: Request corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.
        storage: Armazenamento privado de originais.

    Returns:
        O arquivo original, com o nome e MIME type de upload.

    Raises:
        HTTPException: 404 se a evidência não existir neste tenant/caso, ou
            se o original não estiver disponível no armazenamento.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    evidence = await _get_evidence_or_404(session, tenant_id, case_id, evidence_id)
    try:
        path = storage.read_path(evidence.storage_key)
    except EvidenceStorageError as exc:
        logger.error(
            "evidence.download.missing_original",
            case_id=str(case_id),
            tenant_id=str(tenant_id),
            evidence_id=str(evidence_id),
        )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Arquivo original indisponível no armazenamento.",
        ) from exc

    await record_evidence_access(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        evidence_id=evidence_id,
        actor_id=uuid.UUID(request.state.user_id),
        access_kind="download",
        client_host=request.client.host if request.client else None,
    )
    logger.info(
        "evidence.download",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        evidence_id=str(evidence_id),
    )
    return FileResponse(
        path,
        media_type=evidence.mime_type,
        filename=evidence.original_filename,
    )


@router.post(
    "/{evidence_id}/process",
    response_model=EvidenceFileResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_require_evidence_writer)],
)
async def reprocess_case_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_tenant_session),
    storage: EvidenceStorage = Depends(get_evidence_storage),
) -> EvidenceFile:
    """Dispara (re)processamento da extração de uma evidência, em background.

    Cada execução gera um novo artefato derivado — execuções anteriores nunca
    são apagadas nem sobrescritas, e o original permanece intacto.

    Args:
        case_id: ID do caso.
        evidence_id: ID da evidência.
        request: Request corrente, com `state.tenant_id`.
        background_tasks: Fila de tarefas pós-resposta.
        session: Sessão do banco já escopada por tenant.
        storage: Armazenamento privado de originais.

    Returns:
        Metadados atuais da evidência (o status muda em background).

    Raises:
        HTTPException: 404 se a evidência não existir neste tenant/caso; 409
            se já houver processamento em andamento.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    evidence = await _get_evidence_or_404(session, tenant_id, case_id, evidence_id)
    if evidence.status == EvidenceProcessingStatus.PROCESSING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Evidência já está em processamento."
        )
    background_tasks.add_task(process_evidence, tenant_id, evidence.id, storage)
    logger.info(
        "evidence.reprocess.requested",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        evidence_id=str(evidence_id),
    )
    return evidence


@router.get("/{evidence_id}/extractions", response_model=list[EvidenceExtractionResponse])
async def list_case_evidence_extractions(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list:
    """Lista as execuções de extração de uma evidência (texto derivado).

    O texto extraído sempre vem com confidence e limitations — é conteúdo
    derivado que requer conferência humana, nunca prova perfeita.

    Args:
        case_id: ID do caso.
        evidence_id: ID da evidência.
        request: Request corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Execuções de extração, mais recentes primeiro (sucesso e falha).

    Raises:
        HTTPException: 404 se a evidência não existir neste tenant/caso.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _get_evidence_or_404(session, tenant_id, case_id, evidence_id)
    return await list_extractions(session, tenant_id=tenant_id, evidence_id=evidence_id)


@router.post(
    "/{evidence_id}/extractions/{extraction_id}/review",
    response_model=ExtractionReviewResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_evidence_writer)],
)
async def review_case_evidence_extraction(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    extraction_id: uuid.UUID,
    payload: ExtractionReviewCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> ExtractionReviewResponse:
    """Registra a revisão humana de um texto extraído (Fase 3.5).

    A revisão é um registro auditado — confirmação ou apontamento de erro com
    observação — e nunca substitui o texto derivado nem o original.

    Args:
        case_id: ID do caso.
        evidence_id: ID da evidência.
        extraction_id: Execução de extração revisada.
        payload: Veredito (confirmed | extraction_error) e observação.
        request: Request corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        A revisão registrada.

    Raises:
        HTTPException: 404 se evidência ou extração não existirem neste
            tenant/caso.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _get_evidence_or_404(session, tenant_id, case_id, evidence_id)
    review = await review_extraction(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        extraction_id=extraction_id,
        reviewer_id=uuid.UUID(request.state.user_id),
        verdict=payload.verdict,
        note=payload.note,
    )
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Extração não encontrada.")
    logger.info(
        "evidence.extraction.reviewed",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        evidence_id=str(evidence_id),
        extraction_id=str(extraction_id),
        verdict=payload.verdict.value,
    )
    return review


# --- Análise de evidências (módulo LangGraph — Fase 3.3) ----------------------


def _build_analysis_response(
    case, state: CaseState | dict, findings
) -> EvidenceAnalysisResultResponse:
    """Combina o Case persistido, o checkpoint do CaseState e os achados."""
    raw_assessment = state.get("specialist_assessment")
    assessment = None
    if raw_assessment is not None:
        assessment = SpecialistAssessmentResponse(
            platform_context=raw_assessment.platform_context,
            platform_failure=raw_assessment.platform_failure,
            report_mechanism_analysis=raw_assessment.report_mechanism_analysis,
            preservation_recommendations=raw_assessment.preservation_recommendations,
            hypotheses=raw_assessment.hypotheses,
            status=raw_assessment.status,
        )
    return EvidenceAnalysisResultResponse(
        case_id=case.id,
        evidence_outcome=state.get("evidence_outcome"),
        findings=[EvidenceFindingResponse.model_validate(finding) for finding in findings],
        specialist_assessment=assessment,
        documents_requested=state.get("documents_requested", []),
        human_review_required=case.human_review_required,
        status=case.status,
        current_module=case.current_module,
    )


@router.post(
    "/analysis/run",
    response_model=EvidenceAnalysisResultResponse,
    dependencies=[Depends(_require_evidence_writer)],
)
async def run_case_evidence_analysis(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    llm_client: LLMClient = Depends(get_llm_client),
) -> EvidenceAnalysisResultResponse:
    """Executa documental + specialist (orchestrator/graphs/evidence.py) para um caso.

    O resultado é sempre uma recomendação (CLAUDE.md, seção 2): o caso
    termina aguardando revisão humana e só avança para research via
    `POST .../evidence/analysis/review`.

    Args:
        case_id: ID do caso a analisar.
        request: Request corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.
        llm_client: Provedor de IA (injetado via `get_llm_client`).

    Returns:
        O inventário probatório e a leitura técnica mais recentes.

    Raises:
        HTTPException: 404 se o caso não existir; 422 se o caso não estiver
            pronto (intake não aprovado, sem evidências) ou o CaseState for
            inválido; 502 se a saída do modelo for inválida ou não rastreável;
            503 se nenhum provedor de IA estiver configurado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        outcome = await run_evidence(
            session, tenant_id=tenant_id, case_id=case_id, llm_client=llm_client
        )
    except (EvidenceNotReadyError, EvidenceGraphValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except EvidenceTraceabilityError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"O modelo produziu um achado não rastreável e foi rejeitado: {exc}",
        ) from exc
    except LLMOutputValidationError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="O modelo de IA retornou uma saída inválida."
        ) from exc
    if outcome is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    case, state = outcome
    findings_result = await get_evidence_analysis(
        session, tenant_id=tenant_id, case_id=case_id
    )
    _, _, findings = findings_result if findings_result else (None, {}, [])
    logger.info(
        "evidence.analysis.run",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        outcome=state.get("evidence_outcome"),
        findings=len(findings),
    )
    return _build_analysis_response(case, state, findings)


@router.get("/analysis/result", response_model=EvidenceAnalysisResultResponse)
async def get_case_evidence_analysis(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> EvidenceAnalysisResultResponse:
    """Consulta o resultado mais recente da análise de evidências de um caso.

    Args:
        case_id: ID do caso.
        request: Request corrente, com `state.tenant_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O inventário probatório e a leitura técnica mais recentes.

    Raises:
        HTTPException: 404 se o caso não existir, ou se a análise ainda não
            tiver sido executada.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    result = await get_evidence_analysis(session, tenant_id=tenant_id, case_id=case_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    case, state, findings = result
    if state.get("evidence_outcome") is None and not findings:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="A análise de evidências ainda não foi executada para este caso.",
        )
    return _build_analysis_response(case, state, findings)


@router.post(
    "/analysis/review",
    response_model=EvidenceAnalysisResultResponse,
    dependencies=[Depends(_require_evidence_writer)],
)
async def review_case_evidence_analysis(
    case_id: uuid.UUID,
    payload: EvidenceReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> EvidenceAnalysisResultResponse:
    """Registra a decisão humana sobre o inventário probatório do caso.

    "approve" marca os achados como APPROVED e avança o caso para research;
    "return_for_information" mantém o caso em evidence aguardando novas
    evidências. Nunca aprova nada sozinha (CLAUDE.md, seção 2).

    Args:
        case_id: ID do caso.
        payload: Decisão (approve/return_for_information) e justificativa.
        request: Request corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O estado consolidado após a revisão.

    Raises:
        HTTPException: 404 se o caso não existir; 409 se não houver análise
            pendente de revisão.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        case = await review_evidence_findings(
            session,
            tenant_id=tenant_id,
            case_id=case_id,
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except EvidenceReviewConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    result = await get_evidence_analysis(session, tenant_id=tenant_id, case_id=case_id)
    _, state, findings = result if result else (None, {}, [])
    logger.info(
        "evidence.analysis.review",
        case_id=str(case_id),
        tenant_id=str(tenant_id),
        decision=payload.decision.value,
    )
    return _build_analysis_response(case, state, findings)
