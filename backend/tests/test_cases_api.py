"""Testes da abertura de caso com catálogo, código e cliente (app/api/v1/cases.py)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.models.client import Client
from tests.conftest import TenantFixture, case_payload, login

VALID_CPF = "529.982.247-25"


async def test_case_is_created_with_code_and_denormalized_classification(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = await case_payload(api_client, auth_headers)
    response = await api_client.post("/api/v1/cases", json=payload, headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"].startswith("CAS-")
    assert body["platform_entry"]["id"] == payload["platform_id"]
    assert body["fraud_modality"]["id"] == payload["fraud_modality_id"]
    # platform/fraud_type são derivados da entrada de catálogo, nunca do payload.
    assert body["platform"] == body["platform_entry"]["label"]
    assert body["fraud_type"] == body["fraud_modality"]["family"]


async def test_case_codes_are_sequential_within_the_office(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    codes = []
    for _ in range(3):
        response = await api_client.post(
            "/api/v1/cases",
            json=await case_payload(api_client, auth_headers),
            headers=auth_headers,
        )
        codes.append(response.json()["code"])

    assert [code[-6:] for code in codes] == ["000001", "000002", "000003"]


async def test_case_created_with_nested_client_in_one_transaction(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(
            api_client,
            auth_headers,
            client={
                "full_name": "Marta Ribeiro",
                "document_number": VALID_CPF,
                "address_city": "Santos",
                "address_state": "SP",
            },
        ),
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["client"]["full_name"] == "Marta Ribeiro"
    assert body["client"]["code"].startswith("CLI-")
    assert body["client_id"] == body["client"]["id"]
    # ClientSummary não expõe documento: CPF completo só em /clients/{id}.
    assert "document_number" not in body["client"]


async def test_failed_case_creation_leaves_no_orphan_client(
    api_client: AsyncClient, tenant: TenantFixture, auth_headers: dict[str, str]
) -> None:
    """O cadastro do cliente participa da transação do caso — se o caso falha, volta atrás."""
    payload = await case_payload(
        api_client,
        auth_headers,
        client={"full_name": "Cliente Fantasma", "document_number": VALID_CPF},
    )
    # Modalidade inexistente: a criação do caso falha DEPOIS do cliente ser gravado.
    payload["fraud_modality_id"] = str(uuid.uuid4())

    response = await api_client.post("/api/v1/cases", json=payload, headers=auth_headers)
    assert response.status_code == 404

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        count = await session.scalar(
            select(func.count()).select_from(Client).where(Client.tenant_id == tenant.tenant_id)
        )
    assert count == 0

    listing = await api_client.post(
        "/api/v1/clients/search", json={"search": "Fantasma"}, headers=auth_headers
    )
    assert listing.json() == []


async def test_case_rejects_client_id_and_nested_client_together(
    api_client: AsyncClient, tenant_with_client: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_client)
    response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(
            api_client,
            headers,
            client_id=str(tenant_with_client.client_id),
            client={"full_name": "Ambíguo"},
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_catalog_entry_of_another_tenant_returns_404(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    """A FK sozinha não isola: sem a checagem explícita, um tenant classificaria
    o caso com a entrada de catálogo de outro escritório."""
    headers_a = await login(api_client, tenant)
    headers_b = await login(api_client, other_tenant)

    payload_b = await case_payload(api_client, headers_b)
    payload_a = await case_payload(api_client, headers_a)
    payload_a["platform_id"] = payload_b["platform_id"]

    response = await api_client.post("/api/v1/cases", json=payload_a, headers=headers_a)
    assert response.status_code == 404
    assert "Plataforma" in response.json()["detail"]


async def test_search_finds_case_by_client_name_and_code(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, auth_headers, client={"full_name": "Beatriz Nogueira"}),
        headers=auth_headers,
    )
    code = created.json()["code"]

    await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, auth_headers, client={"full_name": "Outro Cliente"}),
        headers=auth_headers,
    )

    for term in ("Beatriz", "beatriz nogueira", code):
        response = await api_client.post(
            "/api/v1/cases/search", json={"search": term}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert [item["code"] for item in response.json()] == [code], term


async def test_search_and_status_filter_combine(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, auth_headers, matter="golpe do falso boleto"),
        headers=auth_headers,
    )

    matching = await api_client.get(
        "/api/v1/cases",
        params={"search": "boleto", "status": "draft"},
        headers=auth_headers,
    )
    non_matching = await api_client.get(
        "/api/v1/cases",
        params={"search": "boleto", "status": "approved"},
        headers=auth_headers,
    )

    assert len(matching.json()) == 1
    assert non_matching.json() == []


async def test_patch_platform_rederives_denormalized_label(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, auth_headers),
        headers=auth_headers,
    )
    case_id = created.json()["id"]

    platforms = await api_client.get("/api/v1/catalog/platforms", headers=auth_headers)
    shopee = next(entry for entry in platforms.json() if entry["slug"] == "shopee")

    response = await api_client.patch(
        f"/api/v1/cases/{case_id}",
        json={"platform_id": shopee["id"]},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["platform"] == shopee["label"]
    assert response.json()["platform_entry"]["slug"] == "shopee"
