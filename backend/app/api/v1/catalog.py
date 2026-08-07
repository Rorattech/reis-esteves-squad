"""Rotas dos catálogos de classificação do caso — plataformas e modalidades.

As rotas de listagem reconciliam o catálogo de sistema antes de responder
(`ensure_catalog_seeded`): é uma escrita num GET, de propósito. A alternativa
seria semear no POST /auth/register, mas aquela rota usa
`get_auth_bootstrap_session`, cujo bypass de RLS é restrito a tenants/users —
as inserções nos catálogos esbarrariam na policy. Semear aqui, na sessão já
escopada por tenant, também faz escritórios antigos receberem entradas novas
acrescentadas a app/core/catalog_defaults.py, sem migration.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.core.rbac import require_role
from app.models.catalog import FraudModality, Platform
from app.models.enums import UserRole
from app.models.schemas.catalog import (
    FraudModalityCreate,
    FraudModalityResponse,
    PlatformCreate,
    PlatformResponse,
)
from app.services.catalog_service import (
    DuplicateCatalogEntryError,
    create_fraud_modality,
    create_platform,
    ensure_catalog_seeded,
    list_fraud_modalities,
    list_platforms,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Cadastrar uma entrada de catálogo é parte de abrir um caso — mesmo papel.
_require_catalog_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)

_DUPLICATE_DETAIL = "Já existe uma entrada com este nome no catálogo do escritório."


@router.get("/platforms", response_model=list[PlatformResponse])
async def list_platforms_route(
    request: Request,
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Platform]:
    """Lista as plataformas disponíveis para classificar um caso.

    Args:
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        include_inactive: Se True, inclui entradas desativadas.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Plataformas do escritório, na ordem de exibição.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await ensure_catalog_seeded(session, tenant_id=tenant_id)
    platforms = await list_platforms(
        session, tenant_id=tenant_id, include_inactive=include_inactive
    )
    await session.commit()
    return platforms


@router.post(
    "/platforms",
    response_model=PlatformResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_catalog_writer)],
)
async def create_platform_route(
    payload: PlatformCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Platform:
    """Cadastra uma plataforma própria do escritório.

    Args:
        payload: Rótulo da plataforma, digitado na opção "Outro" do formulário.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Plataforma recém-criada.

    Raises:
        HTTPException: 409 se já existir entrada equivalente no catálogo.
    """
    try:
        platform = await create_platform(
            session,
            tenant_id=uuid.UUID(request.state.tenant_id),
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except DuplicateCatalogEntryError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from error

    await session.commit()
    await session.refresh(platform)

    logger.info("catalog.platform.create", slug=platform.slug, tenant_id=request.state.tenant_id)
    return platform


@router.get("/fraud-modalities", response_model=list[FraudModalityResponse])
async def list_fraud_modalities_route(
    request: Request,
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[FraudModality]:
    """Lista as modalidades de golpe disponíveis para classificar um caso.

    Args:
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        include_inactive: Se True, inclui entradas desativadas.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Modalidades do escritório, na ordem de exibição.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    await ensure_catalog_seeded(session, tenant_id=tenant_id)
    modalities = await list_fraud_modalities(
        session, tenant_id=tenant_id, include_inactive=include_inactive
    )
    await session.commit()
    return modalities


@router.post(
    "/fraud-modalities",
    response_model=FraudModalityResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_catalog_writer)],
)
async def create_fraud_modality_route(
    payload: FraudModalityCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> FraudModality:
    """Cadastra uma modalidade de golpe própria do escritório.

    Args:
        payload: Rótulo e família da modalidade. A família é obrigatória — é o
            que o grafo e os prompts leem (ver app/models/catalog.py).
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Modalidade recém-criada.

    Raises:
        HTTPException: 409 se já existir entrada equivalente no catálogo.
    """
    try:
        modality = await create_fraud_modality(
            session,
            tenant_id=uuid.UUID(request.state.tenant_id),
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except DuplicateCatalogEntryError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from error

    await session.commit()
    await session.refresh(modality)

    logger.info(
        "catalog.fraud_modality.create",
        slug=modality.slug,
        tenant_id=request.state.tenant_id,
    )
    return modality
