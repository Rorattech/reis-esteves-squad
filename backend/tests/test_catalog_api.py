"""Testes dos catálogos de classificação (app/api/v1/catalog.py)."""

from httpx import AsyncClient
from sqlalchemy import select

from app.core.catalog_defaults import DEFAULT_FRAUD_MODALITIES, DEFAULT_PLATFORMS
from app.core.db import async_session_factory, scope_session_to_tenant
from app.models.catalog import Platform
from tests.conftest import TenantFixture, login


async def test_listing_seeds_the_default_catalog(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """O catálogo é semeado sob demanda: um tenant novo já lista as entradas padrão."""
    platforms = await api_client.get("/api/v1/catalog/platforms", headers=auth_headers)
    modalities = await api_client.get("/api/v1/catalog/fraud-modalities", headers=auth_headers)

    assert platforms.status_code == 200, platforms.text
    assert modalities.status_code == 200, modalities.text
    assert {entry["slug"] for entry in platforms.json()} == {
        entry.slug for entry in DEFAULT_PLATFORMS
    }
    assert {entry["slug"] for entry in modalities.json()} == {
        entry.slug for entry in DEFAULT_FRAUD_MODALITIES
    }
    assert all(entry["is_system"] for entry in platforms.json())


async def test_seeding_is_idempotent(
    api_client: AsyncClient, tenant: TenantFixture, auth_headers: dict[str, str]
) -> None:
    for _ in range(3):
        response = await api_client.get("/api/v1/catalog/platforms", headers=auth_headers)
        assert response.status_code == 200

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        rows = await session.scalars(select(Platform).where(Platform.tenant_id == tenant.tenant_id))

    assert len(list(rows.all())) == len(DEFAULT_PLATFORMS)


async def test_platforms_are_ordered_for_display(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.get("/api/v1/catalog/platforms", headers=auth_headers)
    orders = [entry["sort_order"] for entry in response.json()]
    assert orders == sorted(orders)
    # "Outra plataforma" é a última opção do select, nunca a primeira.
    assert response.json()[-1]["slug"] == "outra_plataforma"


async def test_create_custom_modality_with_family(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """É o caminho da opção "Outro": vocabulário livre, ancorado numa família."""
    response = await api_client.post(
        "/api/v1/catalog/fraud-modalities",
        json={"label": "Golpe da Falsa Central de Atendimento", "family": "pix"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "golpe_da_falsa_central_de_atendimento"
    assert body["family"] == "pix"
    assert body["is_system"] is False

    listing = await api_client.get("/api/v1/catalog/fraud-modalities", headers=auth_headers)
    assert body["id"] in {entry["id"] for entry in listing.json()}


async def test_custom_modality_requires_family(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Sem família a modalidade seria texto que o grafo não sabe interpretar."""
    response = await api_client.post(
        "/api/v1/catalog/fraud-modalities",
        json={"label": "Modalidade sem família"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_duplicate_label_is_conflict(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"label": "Leilão Falso"}
    first = await api_client.post("/api/v1/catalog/platforms", json=payload, headers=auth_headers)
    assert first.status_code == 201

    # O slug é derivado do label, então variação de caixa/acento colide.
    duplicate = await api_client.post(
        "/api/v1/catalog/platforms",
        json={"label": "leilão falso"},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409


async def test_custom_entry_is_not_visible_to_another_tenant(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    headers_a = await login(api_client, tenant)
    headers_b = await login(api_client, other_tenant)

    created = await api_client.post(
        "/api/v1/catalog/platforms",
        json={"label": "Plataforma Interna A"},
        headers=headers_a,
    )
    assert created.status_code == 201

    listing_b = await api_client.get("/api/v1/catalog/platforms", headers=headers_b)
    assert "plataforma_interna_a" not in {entry["slug"] for entry in listing_b.json()}


async def test_viewer_can_read_but_not_create(
    api_client: AsyncClient, viewer_tenant: TenantFixture
) -> None:
    headers = await login(api_client, viewer_tenant)

    listing = await api_client.get("/api/v1/catalog/platforms", headers=headers)
    assert listing.status_code == 200

    created = await api_client.post(
        "/api/v1/catalog/platforms", json={"label": "Tentativa"}, headers=headers
    )
    assert created.status_code == 403
