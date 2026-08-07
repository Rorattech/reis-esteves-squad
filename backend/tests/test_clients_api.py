"""Testes das rotas de cadastro de clientes (app/api/v1/clients.py)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.models.audit_log import AuditLog
from tests.conftest import TenantFixture, login

#: CPF e CNPJ estruturalmente válidos, usados como dados fictícios de teste.
VALID_CPF = "529.982.247-25"
VALID_CPF_DIGITS = "52998224725"
OTHER_VALID_CPF = "168.995.350-09"
VALID_CNPJ = "11.222.333/0001-81"

FULL_CLIENT = {
    "full_name": "Maria Souza de Oliveira",
    "person_type": "individual",
    "document_number": VALID_CPF,
    "email": "maria@example.com.br",
    "phone": "(11) 98765-4321",
    "rg": "12.345.678-9",
    "rg_issuer": "SSP/SP",
    "birth_date": "1985-03-14",
    "nationality": "brasileira",
    "marital_status": "married",
    "profession": "professora",
    "address_street": "Rua das Acácias",
    "address_number": "220",
    "address_complement": "apto 51",
    "address_district": "Vila Mariana",
    "address_city": "São Paulo",
    "address_state": "sp",
    "address_zip_code": "01310-100",
}


async def test_create_client_returns_full_qualification_and_code(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"].startswith("CLI-")
    assert body["full_name"] == "Maria Souza de Oliveira"
    assert body["profession"] == "professora"
    assert body["marital_status"] == "married"
    # Documento e CEP são normalizados; a UF é normalizada para maiúsculas.
    assert body["document_number"] == VALID_CPF_DIGITS
    assert body["address_zip_code"] == "01310100"
    assert body["address_state"] == "SP"


async def test_create_client_rejects_invalid_cpf(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/clients",
        json={"full_name": "CPF Inválido", "document_number": "529.982.247-24"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_create_client_rejects_cnpj_for_individual(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Natureza e documento têm de casar — senão um CNPJ entraria como CPF na peça."""
    response = await api_client.post(
        "/api/v1/clients",
        json={
            "full_name": "Pessoa Física com CNPJ",
            "person_type": "individual",
            "document_number": VALID_CNPJ,
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_create_client_accepts_company_with_cnpj(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/clients",
        json={
            "full_name": "Comércio Exemplo LTDA",
            "person_type": "company",
            "document_number": VALID_CNPJ,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["document_number"] == "11222333000181"


async def test_duplicate_document_in_same_tenant_is_conflict(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)
    assert first.status_code == 201

    # Mesmo CPF sem máscara: a normalização é o que faz o conflito ser detectado.
    duplicate = await api_client.post(
        "/api/v1/clients",
        json={"full_name": "Outro Nome", "document_number": VALID_CPF_DIGITS},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409
    assert "CPF/CNPJ" in duplicate.json()["detail"]


async def test_same_document_in_another_tenant_is_allowed(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    """A unicidade é por escritório: o mesmo cliente pode ser atendido por dois."""
    headers_a = await login(api_client, tenant)
    headers_b = await login(api_client, other_tenant)

    first = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=headers_a)
    second = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=headers_b)

    assert first.status_code == 201
    assert second.status_code == 201, second.text
    # Cada escritório numera do próprio começo.
    assert first.json()["code"] == second.json()["code"] == "CLI-000001"


async def test_multiple_clients_without_document_do_not_collide(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Documento é opcional no primeiro contato — vários NULLs não podem colidir."""
    for name in ("Sem Documento Um", "Sem Documento Dois"):
        response = await api_client.post(
            "/api/v1/clients", json={"full_name": name}, headers=auth_headers
        )
        assert response.status_code == 201, response.text


async def test_search_never_puts_personal_data_in_the_url(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A busca é POST: CPF e nome não podem aparecer em access log, histórico
    de navegador, cabeçalho Referer nem cache de proxy (CLAUDE.md, seção 12)."""
    await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)

    response = await api_client.post(
        "/api/v1/clients/search", json={"search": VALID_CPF}, headers=auth_headers
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.json()] == ["CLI-000001"]
    # O termo vai no corpo — a URL não carrega nada do documento.
    url = str(response.request.url)
    assert VALID_CPF not in url
    assert VALID_CPF_DIGITS not in url


async def test_search_by_name_document_and_code(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)
    code = created.json()["code"]
    await api_client.post(
        "/api/v1/clients",
        json={"full_name": "João Pereira", "document_number": OTHER_VALID_CPF},
        headers=auth_headers,
    )

    for term in ("Maria", "maria souza", VALID_CPF, VALID_CPF_DIGITS, code):
        response = await api_client.post(
            "/api/v1/clients/search", json={"search": term}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        results = response.json()
        assert [item["full_name"] for item in results] == ["Maria Souza de Oliveira"], term


async def test_search_without_term_lists_clients_by_name(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for name in ("Zulmira Alves", "Ana Beatriz"):
        await api_client.post("/api/v1/clients", json={"full_name": name}, headers=auth_headers)

    response = await api_client.get("/api/v1/clients", headers=auth_headers)
    assert response.status_code == 200
    assert [item["full_name"] for item in response.json()] == [
        "Ana Beatriz",
        "Zulmira Alves",
    ]


async def test_client_of_another_tenant_returns_404(
    api_client: AsyncClient, tenant: TenantFixture, other_tenant: TenantFixture
) -> None:
    headers_a = await login(api_client, tenant)
    created = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=headers_a)
    client_id = created.json()["id"]

    headers_b = await login(api_client, other_tenant)
    response = await api_client.get(f"/api/v1/clients/{client_id}", headers=headers_b)
    assert response.status_code == 404

    # A busca do outro tenant também não pode enxergar nada.
    listing = await api_client.get("/api/v1/clients", params={"search": "Maria"}, headers=headers_b)
    assert listing.json() == []


async def test_unknown_client_returns_404(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.get(f"/api/v1/clients/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


async def test_update_client_changes_qualification(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)
    client_id = created.json()["id"]

    response = await api_client.patch(
        f"/api/v1/clients/{client_id}",
        json={"profession": "coordenadora pedagógica", "address_city": "Santos"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profession"] == "coordenadora pedagógica"
    assert body["address_city"] == "Santos"
    # Campos não enviados permanecem intactos (semântica PATCH).
    assert body["full_name"] == "Maria Souza de Oliveira"


async def test_update_rejects_document_of_another_client(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)
    second = await api_client.post(
        "/api/v1/clients",
        json={"full_name": "João Pereira", "document_number": OTHER_VALID_CPF},
        headers=auth_headers,
    )

    response = await api_client.patch(
        f"/api/v1/clients/{second.json()['id']}",
        json={"document_number": VALID_CPF},
        headers=auth_headers,
    )
    assert response.status_code == 409


async def test_update_rejects_person_type_that_contradicts_stored_document(
    api_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A validação olha o estado FINAL: trocar só a natureza deixaria um CPF como CNPJ."""
    created = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=auth_headers)

    response = await api_client.patch(
        f"/api/v1/clients/{created.json()['id']}",
        json={"person_type": "company"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_viewer_can_read_but_not_write(
    api_client: AsyncClient, tenant: TenantFixture, viewer_tenant: TenantFixture
) -> None:
    viewer_headers = await login(api_client, viewer_tenant)

    created = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=viewer_headers)
    assert created.status_code == 403

    listing = await api_client.get("/api/v1/clients", headers=viewer_headers)
    assert listing.status_code == 200


async def test_audit_records_client_creation_without_personal_data(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    headers = await login(api_client, tenant)
    response = await api_client.post("/api/v1/clients", json=FULL_CLIENT, headers=headers)
    assert response.status_code == 201

    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.tenant_id,
                AuditLog.action == "cadastrou cliente",
            )
        )

    assert audit is not None
    assert audit.case_id is None
    # Só hashes e identificadores sobrevivem — nenhum dado pessoal em claro
    # (CLAUDE.md, seção 12).
    serialized = f"{audit.input_hash}{audit.output_hash}{audit.metadata_}"
    assert VALID_CPF_DIGITS not in serialized
    assert "Maria Souza" not in serialized
    assert "01310100" not in serialized
    assert audit.metadata_["entity"] == "client"
