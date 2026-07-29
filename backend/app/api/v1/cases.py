"""Rotas de casos jurídicos (CLAUDE.md, seção 7 — multitenancy obrigatória).

Todas as rotas exigem TenantMiddleware (JWT válido, ver app/middleware/tenant.py)
e usam a sessão já escopada por tenant injetada em request.state.db via
get_tenant_session — nunca abrem uma sessão própria nem aceitam tenant_id/
user_id vindos do payload do cliente (ver comentário em schemas/case.py).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.core.rbac import require_role
from app.models.case import Case
from app.models.client import Client
from app.models.enums import UserRole
from app.models.schemas.case import CaseCreate, CaseResponse, CaseUpdate

logger = structlog.get_logger()

router = APIRouter(prefix="/cases", tags=["cases"])

# viewer só lê; abrir/editar um caso exige um papel operacional (CLAUDE.md, seção 12).
_require_case_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)


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

    Args:
        payload: Dados do caso — plataforma, modalidade do golpe e urgência.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`
            definidos pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Caso recém-criado.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await _ensure_client_belongs_to_tenant(session, tenant_id, payload.client_id)

    case = Case(
        tenant_id=tenant_id,
        user_id=uuid.UUID(request.state.user_id),
        platform=payload.platform,
        fraud_type=payload.fraud_type,
        urgency=payload.urgency,
        client_id=payload.client_id,
        area=payload.area,
        matter=payload.matter,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)

    logger.info("cases.create", case_id=str(case.id), tenant_id=request.state.tenant_id)
    return case


@router.get("", response_model=list[CaseResponse])
async def list_cases(
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Case]:
    """Lista os casos do tenant autenticado, mais recentes primeiro.

    Args:
        request: Request HTTP corrente, com `state.tenant_id` definido pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Casos do tenant autenticado.
    """
    cases = await session.scalars(
        select(Case)
        .where(Case.tenant_id == uuid.UUID(request.state.tenant_id))
        .order_by(Case.created_at.desc())
    )
    return list(cases.all())


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
    case = await session.scalar(
        select(Case).where(
            Case.tenant_id == uuid.UUID(request.state.tenant_id),
            Case.id == case_id,
        )
    )
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    return case


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

    Args:
        case_id: ID do caso.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).
        request: Request HTTP corrente, com `state.tenant_id` definido pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O caso atualizado.

    Raises:
        HTTPException: 404 se o caso não existir neste tenant.
    """
    case = await session.scalar(
        select(Case).where(
            Case.tenant_id == uuid.UUID(request.state.tenant_id),
            Case.id == case_id,
        )
    )
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")

    updates = payload.model_dump(exclude_unset=True)
    if "client_id" in updates:
        await _ensure_client_belongs_to_tenant(
            session, uuid.UUID(request.state.tenant_id), updates["client_id"]
        )
    for field, value in updates.items():
        setattr(case, field, value)

    await session.commit()
    await session.refresh(case)

    logger.info("cases.update", case_id=str(case.id), tenant_id=request.state.tenant_id)
    return case
