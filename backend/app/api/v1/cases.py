"""Rotas de casos jurídicos (CLAUDE.md, seção 7 — multitenancy obrigatória).

Todas as rotas exigem TenantMiddleware (JWT válido, ver app/middleware/tenant.py)
e usam a sessão já escopada por tenant injetada em request.state.db via
get_tenant_session — nunca abrem uma sessão própria nem aceitam tenant_id/
user_id vindos do payload do cliente (ver comentário em schemas/case.py).
"""

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.db import get_tenant_session
from app.core.identifiers import CodeScope, next_code
from app.core.rbac import require_role
from app.models.case import Case
from app.models.catalog import FraudModality, Platform
from app.models.client import Client
from app.models.enums import CaseStatus, UserRole
from app.models.schemas.case import (
    CaseCreate,
    CaseResponse,
    CaseSearchRequest,
    CaseUpdate,
)
from app.services.client_service import (
    DocumentPersonTypeMismatchError,
    DuplicateClientDocumentError,
    create_client,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/cases", tags=["cases"])

# Não há chamada a modelo de IA nesta camada — "n/a" é o valor convencionado
# no projeto para ações puramente humanas (ver app/services/client_service.py).
_MODEL_USED_MANUAL = "n/a"

# viewer só lê; abrir/editar um caso exige um papel operacional (CLAUDE.md, seção 12).
_require_case_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)
# Excluir é destrutivo e irreversível — mais restrito que editar: paralegal não exclui.
_require_case_deleter = require_role(UserRole.ADMIN, UserRole.LAWYER)

#: Relacionamentos que CaseResponse serializa. Sem o eager load, o Pydantic
#: dispararia lazy loads em contexto async e estouraria MissingGreenlet.
CASE_RESPONSE_RELATIONSHIPS = (
    selectinload(Case.client),
    selectinload(Case.platform_entry),
    selectinload(Case.fraud_modality),
)


async def _ensure_client_belongs_to_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, client_id: uuid.UUID | None
) -> None:
    """Impede vincular um caso a um client_id de outro tenant.

    A FK cases.client_id -> clients.id, por si só, não garante isolamento de
    tenant (RLS valida apenas tenant_id da própria linha de `cases`) — sem
    esta checagem, um tenant malicioso poderia referenciar o client_id de
    outro tenant, violando CLAUDE.md seção 7.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        client_id: client_id informado no payload, se houver.

    Raises:
        HTTPException: 404 se client_id não existir neste tenant.
    """
    if client_id is None:
        return
    client = await session.scalar(
        select(Client.id).where(Client.tenant_id == tenant_id, Client.id == client_id)
    )
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")


async def _resolve_platform(
    session: AsyncSession, tenant_id: uuid.UUID, platform_id: uuid.UUID
) -> Platform:
    """Carrega a plataforma do catálogo do próprio tenant.

    Mesmo motivo de `_ensure_client_belongs_to_tenant`: a FK não impede
    apontar para a entrada de catálogo de outro escritório.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        platform_id: Entrada de catálogo informada no payload.

    Returns:
        A plataforma correspondente.

    Raises:
        HTTPException: 404 se a plataforma não existir neste tenant.
    """
    platform = await session.scalar(
        select(Platform).where(Platform.tenant_id == tenant_id, Platform.id == platform_id)
    )
    if platform is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Plataforma não encontrada no catálogo."
        )
    return platform


async def _resolve_fraud_modality(
    session: AsyncSession, tenant_id: uuid.UUID, fraud_modality_id: uuid.UUID
) -> FraudModality:
    """Carrega a modalidade do catálogo do próprio tenant.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        fraud_modality_id: Entrada de catálogo informada no payload.

    Returns:
        A modalidade correspondente.

    Raises:
        HTTPException: 404 se a modalidade não existir neste tenant.
    """
    modality = await session.scalar(
        select(FraudModality).where(
            FraudModality.tenant_id == tenant_id, FraudModality.id == fraud_modality_id
        )
    )
    if modality is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Modalidade não encontrada no catálogo."
        )
    return modality


async def load_case_for_response(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case:
    """Recarrega um caso com os relacionamentos que a resposta serializa.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.

    Returns:
        O caso com cliente e entradas de catálogo já carregados.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    case = await session.scalar(
        select(Case)
        .where(Case.tenant_id == tenant_id, Case.id == case_id)
        .options(*CASE_RESPONSE_RELATIONSHIPS)
    )
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    return case


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_case_writer)],
)
async def create_case(
    payload: CaseCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Case:
    """Abre um novo caso para o tenant e usuário autenticados.

    Quando o payload traz `client`, o cliente é cadastrado na mesma transação
    do caso: se a abertura falhar, o cadastro volta atrás junto e nenhum
    cliente órfão fica na base.

    Args:
        payload: Classificação do caso e cliente (existente ou novo).
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`
            definidos pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Caso recém-criado, com o código legível emitido.

    Raises:
        HTTPException: 404 se cliente/plataforma/modalidade não existirem neste
            tenant; 409 se o documento do cliente novo já estiver cadastrado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    user_id = uuid.UUID(request.state.user_id)

    platform = await _resolve_platform(session, tenant_id, payload.platform_id)
    modality = await _resolve_fraud_modality(session, tenant_id, payload.fraud_modality_id)

    client_id = payload.client_id
    if payload.client is not None:
        try:
            client = await create_client(
                session, tenant_id=tenant_id, actor_id=user_id, payload=payload.client
            )
        except DuplicateClientDocumentError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Já existe um cliente com este CPF/CNPJ neste escritório.",
            ) from error
        except DocumentPersonTypeMismatchError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Documento incompatível com a natureza do cliente — pessoa "
                    "física usa CPF e pessoa jurídica usa CNPJ."
                ),
            ) from error
        client_id = client.id
    else:
        await _ensure_client_belongs_to_tenant(session, tenant_id, client_id)

    case = Case(
        tenant_id=tenant_id,
        user_id=user_id,
        code=await next_code(session, tenant_id=tenant_id, scope=CodeScope.CASE),
        platform_id=platform.id,
        fraud_modality_id=modality.id,
        # Rótulo e família denormalizados da entrada de catálogo — nunca do
        # payload (ver app/models/case.py).
        platform=platform.label,
        fraud_type=modality.family,
        urgency=payload.urgency,
        client_id=client_id,
        area=payload.area,
        matter=payload.matter,
    )
    session.add(case)
    await session.commit()

    logger.info("cases.create", case_code=case.code, tenant_id=request.state.tenant_id)
    return await load_case_for_response(session, tenant_id, case.id)


async def _query_cases(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    search: str | None = None,
    case_status: CaseStatus | None = None,
) -> list[Case]:
    """Lista os casos do tenant, aplicando busca e filtro de status.

    A busca acontece no servidor, e não no navegador, porque passou a incluir o
    nome do cliente: filtrar no cliente exigiria mandar a base de casos
    inteira — com os nomes junto — para toda sessão aberta.
    """
    query = select(Case).where(Case.tenant_id == tenant_id).options(*CASE_RESPONSE_RELATIONSHIPS)

    if case_status is not None:
        query = query.where(Case.status == case_status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.outerjoin(Client, Case.client_id == Client.id).where(
            or_(
                Case.code.ilike(term),
                Case.platform.ilike(term),
                Case.matter.ilike(term),
                Client.full_name.ilike(term),
                Client.code.ilike(term),
            )
        )

    cases = await session.scalars(query.order_by(Case.created_at.desc()))
    return list(cases.all())


@router.post("/search", response_model=list[CaseResponse])
async def search_cases(
    payload: CaseSearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Case]:
    """Busca casos do tenant autenticado, mais recentes primeiro.

    É POST apesar de ser uma leitura: o termo casa com o nome do cliente, e
    query string vaza para access log, histórico do navegador, cabeçalho
    Referer e cache de proxy (CLAUDE.md, seção 12).

    Args:
        payload: Termo de busca e filtro de status.
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Casos do tenant autenticado que casam com os filtros.
    """
    return await _query_cases(
        session,
        tenant_id=uuid.UUID(request.state.tenant_id),
        search=payload.search,
        case_status=payload.status,
    )


@router.get("", response_model=list[CaseResponse])
async def list_cases(
    request: Request,
    case_status: CaseStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Case]:
    """Lista os casos do tenant autenticado, mais recentes primeiro.

    Sem parâmetro de busca de propósito — buscar é `POST /cases/search`, para
    que nenhum dado pessoal apareça na URL. `status` fica aqui por não ser PII.

    Args:
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        case_status: Filtro por status do caso.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Casos do tenant autenticado.
    """
    return await _query_cases(
        session, tenant_id=uuid.UUID(request.state.tenant_id), case_status=case_status
    )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Case:
    """Retorna um caso específico do tenant autenticado.

    Args:
        case_id: ID do caso.
        request: Request HTTP corrente, com `state.tenant_id` definido pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O caso solicitado.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    return await load_case_for_response(session, uuid.UUID(request.state.tenant_id), case_id)


@router.patch(
    "/{case_id}",
    response_model=CaseResponse,
    dependencies=[Depends(_require_case_writer)],
)
async def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Case:
    """Atualiza campos de um caso existente do tenant autenticado.

    Trocar a entrada de catálogo re-deriva os campos denormalizados `platform`
    e `fraud_type` — eles nunca são escritos direto (ver app/models/case.py).

    Args:
        case_id: ID do caso.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).
        request: Request HTTP corrente, com `state.tenant_id` definido pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O caso atualizado.

    Raises:
        HTTPException: 404 se o caso, o cliente ou a entrada de catálogo não
            existirem neste tenant.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    case = await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    updates = payload.model_dump(exclude_unset=True)

    if "client_id" in updates:
        await _ensure_client_belongs_to_tenant(session, tenant_id, updates["client_id"])
    if updates.get("platform_id") is not None:
        platform = await _resolve_platform(session, tenant_id, updates["platform_id"])
        case.platform = platform.label
    if updates.get("fraud_modality_id") is not None:
        modality = await _resolve_fraud_modality(session, tenant_id, updates["fraud_modality_id"])
        case.fraud_type = modality.family

    for field, value in updates.items():
        setattr(case, field, value)

    await session.commit()

    logger.info("cases.update", case_code=case.code, tenant_id=request.state.tenant_id)
    return await load_case_for_response(session, tenant_id, case_id)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_case_deleter)],
)
async def delete_case(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Exclui um caso do tenant autenticado e todo o material ligado a ele.

    Ação destrutiva e irreversível: leva junto relato, checklist, evidências
    e checkpoints do caso (cascade — ver relacionamentos em
    app/models/case.py). Restrita a admin/lawyer: paralegal e viewer não
    excluem casos (CLAUDE.md, seção 12). O registro em audit_logs sobrevive à
    exclusão do caso para o histórico do escritório não ficar com um buraco.

    Args:
        case_id: ID do caso a excluir.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Raises:
        HTTPException: 403 se o papel não puder excluir; 404 se o caso não
            existir neste tenant.
    """
    started_at = time.monotonic()
    tenant_id = uuid.UUID(request.state.tenant_id)
    case = await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    entry = create_audit_entry(
        actor_id=request.state.user_id,
        action="excluiu o caso",
        module=case.current_module.value,
        input_data={"case_id": str(case_id)},
        output_data={"deleted": True},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={
            "case_code": case.code,
            "platform": case.platform,
            "fraud_type": case.fraud_type.value,
        },
    )
    # case_id=None: a linha de audit_logs precisa sobreviver ao DELETE do caso
    # (audit_logs.case_id tem cascade — ver app/models/case.py).
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))

    await session.delete(case)
    await session.commit()

    logger.info("cases.delete", case_code=case.code, tenant_id=request.state.tenant_id)
