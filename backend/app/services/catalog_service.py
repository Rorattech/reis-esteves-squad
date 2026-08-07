"""Serviço dos catálogos de classificação do caso — Fase 2.7.

Toda função recebe tenant_id explícito (nunca inferido do payload) e as
escritas gravam uma entrada em audit_logs antes de retornar (CLAUDE.md, seções
7 e 10). Não há chamada a modelo de IA nesta camada — model_used="n/a" é o
valor convencionado no projeto para ações puramente humanas (ver
app/services/client_service.py).

O commit é responsabilidade do chamador: cadastrar uma modalidade nova pode
fazer parte da mesma transação que abre o caso (ver app/api/v1/cases.py).
"""

import re
import time
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.catalog_defaults import DEFAULT_FRAUD_MODALITIES, DEFAULT_PLATFORMS
from app.models.catalog import FraudModality, Platform
from app.models.schemas.catalog import FraudModalityCreate, PlatformCreate

_MODEL_USED_MANUAL = "n/a"

#: Entradas cadastradas pelo escritório ficam depois das de sistema no select.
_CUSTOM_SORT_ORDER = 500

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class DuplicateCatalogEntryError(Exception):
    """Já existe uma entrada com o mesmo rótulo neste catálogo do escritório."""


def slugify(label: str) -> str:
    """Converte um rótulo livre em slug ASCII estável.

    Args:
        label: Texto digitado pelo advogado (ex.: "Golpe da Falsa Central").

    Returns:
        Slug em snake_case sem acentos (ex.: "golpe_da_falsa_central").
    """
    normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    return _NON_ALNUM.sub("_", normalized.lower()).strip("_")


async def ensure_catalog_seeded(session: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Garante que o escritório tem todas as entradas de sistema do catálogo.

    Reconcilia por slug, não por "a tabela está vazia": assim uma plataforma
    acrescentada a app/core/catalog_defaults.py depois passa a aparecer para os
    escritórios que já existiam, sem migration nova. Entradas que o escritório
    renomeou ou desativou não são tocadas — o ON CONFLICT DO NOTHING só evita
    recriar o que já existe.

    Não faz commit: participa da transação de quem chamou.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
    """
    existing_platforms = set(
        (await session.scalars(select(Platform.slug).where(Platform.tenant_id == tenant_id))).all()
    )
    for entry in DEFAULT_PLATFORMS:
        if entry.slug not in existing_platforms:
            session.add(
                Platform(
                    tenant_id=tenant_id,
                    slug=entry.slug,
                    label=entry.label,
                    is_system=True,
                    sort_order=entry.sort_order,
                )
            )

    existing_modalities = set(
        (
            await session.scalars(
                select(FraudModality.slug).where(FraudModality.tenant_id == tenant_id)
            )
        ).all()
    )
    for modality in DEFAULT_FRAUD_MODALITIES:
        if modality.slug not in existing_modalities:
            session.add(
                FraudModality(
                    tenant_id=tenant_id,
                    slug=modality.slug,
                    label=modality.label,
                    family=modality.family,
                    is_system=True,
                    sort_order=modality.sort_order,
                )
            )

    await session.flush()


async def list_platforms(
    session: AsyncSession, *, tenant_id: uuid.UUID, include_inactive: bool = False
) -> list[Platform]:
    """Lista as plataformas do catálogo do escritório, na ordem de exibição.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        include_inactive: Se True, inclui entradas desativadas (para telas de
            administração do catálogo).

    Returns:
        Plataformas ordenadas por sort_order e depois por label.
    """
    query = select(Platform).where(Platform.tenant_id == tenant_id)
    if not include_inactive:
        query = query.where(Platform.active.is_(True))
    result = await session.scalars(query.order_by(Platform.sort_order, Platform.label))
    return list(result.all())


async def list_fraud_modalities(
    session: AsyncSession, *, tenant_id: uuid.UUID, include_inactive: bool = False
) -> list[FraudModality]:
    """Lista as modalidades de golpe do catálogo do escritório, na ordem de exibição.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        include_inactive: Se True, inclui entradas desativadas.

    Returns:
        Modalidades ordenadas por sort_order e depois por label.
    """
    query = select(FraudModality).where(FraudModality.tenant_id == tenant_id)
    if not include_inactive:
        query = query.where(FraudModality.active.is_(True))
    result = await session.scalars(query.order_by(FraudModality.sort_order, FraudModality.label))
    return list(result.all())


async def _reject_duplicate(
    session: AsyncSession,
    *,
    model: type[Platform] | type[FraudModality],
    tenant_id: uuid.UUID,
    slug: str,
) -> None:
    """Levanta DuplicateCatalogEntryError se o slug já existir no catálogo do tenant."""
    existing = await session.scalar(
        select(model.id).where(model.tenant_id == tenant_id, model.slug == slug)
    )
    if existing is not None:
        raise DuplicateCatalogEntryError(slug)


async def create_platform(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: PlatformCreate,
) -> Platform:
    """Cadastra uma plataforma própria do escritório (opção "Outro").

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        payload: Rótulo da nova plataforma.

    Returns:
        Plataforma recém-criada, ainda não commitada.

    Raises:
        DuplicateCatalogEntryError: Se já existir entrada com o mesmo slug.
    """
    started_at = time.monotonic()
    slug = slugify(payload.label)
    await _reject_duplicate(session, model=Platform, tenant_id=tenant_id, slug=slug)

    platform = Platform(
        tenant_id=tenant_id,
        slug=slug,
        label=payload.label,
        is_system=False,
        sort_order=_CUSTOM_SORT_ORDER,
        created_by=actor_id,
    )
    session.add(platform)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="cadastrou plataforma no catálogo",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"platform_id": str(platform.id), "slug": slug},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "platform", "platform_id": str(platform.id), "slug": slug},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))
    return platform


async def create_fraud_modality(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: FraudModalityCreate,
) -> FraudModality:
    """Cadastra uma modalidade de golpe própria do escritório (opção "Outro").

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        payload: Rótulo e família da nova modalidade.

    Returns:
        Modalidade recém-criada, ainda não commitada.

    Raises:
        DuplicateCatalogEntryError: Se já existir entrada com o mesmo slug.
    """
    started_at = time.monotonic()
    slug = slugify(payload.label)
    await _reject_duplicate(session, model=FraudModality, tenant_id=tenant_id, slug=slug)

    modality = FraudModality(
        tenant_id=tenant_id,
        slug=slug,
        label=payload.label,
        family=payload.family,
        is_system=False,
        sort_order=_CUSTOM_SORT_ORDER,
        created_by=actor_id,
    )
    session.add(modality)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="cadastrou modalidade de golpe no catálogo",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"fraud_modality_id": str(modality.id), "slug": slug},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={
            "entity": "fraud_modality",
            "fraud_modality_id": str(modality.id),
            "slug": slug,
            "family": payload.family.value,
        },
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))
    return modality
