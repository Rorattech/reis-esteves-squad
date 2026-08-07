"""Testes das rotas de evidências (Fase 3.1 — roadmap: autorização, isolamento
por tenant, tipo inválido, arquivo duplicado e auditoria)."""

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.core.security import hash_password
from app.core.storage import EvidenceStorage, get_evidence_storage
from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import TenantFixture, case_payload, login

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_TXT_BYTES = "conversa exportada do whatsapp\ncliente: fui vitima de golpe".encode()


@pytest_asyncio.fixture
async def storage_root(tmp_path: Path) -> AsyncIterator[Path]:
    """Redireciona o EvidenceStorage para um diretório temporário do teste."""
    storage = EvidenceStorage(tmp_path)
    app.dependency_overrides[get_evidence_storage] = lambda: storage
    try:
        yield tmp_path
    finally:
        app.dependency_overrides.pop(get_evidence_storage, None)


async def _upload(
    api_client: AsyncClient,
    headers: dict[str, str],
    case_id: uuid.UUID | str,
    *,
    filename: str = "print-conversa.png",
    content: bytes = _PNG_BYTES,
    mime_type: str = "image/png",
) -> tuple[int, dict]:
    response = await api_client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": (filename, content, mime_type)},
        headers=headers,
    )
    return response.status_code, response.json()


async def _audit_entries(tenant_id: uuid.UUID, evidence_id: str) -> list[AuditLog]:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_id)
        rows = await session.scalars(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.metadata_["evidence_id"].as_string() == evidence_id,
            )
        )
        return list(rows.all())


async def test_upload_stores_original_with_hash(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    status_code, body = await _upload(api_client, auth_headers, tenant_with_case.case_id)
    assert status_code == 201, body

    assert body["sha256_hash"] == hashlib.sha256(_PNG_BYTES).hexdigest()
    assert body["status"] == "received"
    assert body["is_duplicate"] is False
    assert body["extension"] == "png"
    # Detalhe interno de armazenamento nunca sai pela API.
    assert "storage_key" not in body

    # Original gravado intacto no layout <tenant>/<case>/<evidence>/original.<ext>.
    original = (
        storage_root
        / str(tenant_with_case.tenant_id)
        / str(tenant_with_case.case_id)
        / body["id"]
        / "original.png"
    )
    assert original.read_bytes() == _PNG_BYTES


async def test_upload_rejects_unsupported_mime_type(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    status_code, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="planilha.xlsx",
        mime_type="application/vnd.ms-excel",
    )
    assert status_code == 422
    assert "não suportado" in body["detail"]


async def test_upload_rejects_content_mismatching_mime(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    # Declara PNG mas envia texto puro — a assinatura binária não confere.
    status_code, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        content=_TXT_BYTES,
        mime_type="image/png",
    )
    assert status_code == 422
    assert "não corresponde" in body["detail"]


async def test_upload_rejects_empty_file(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    status_code, _ = await _upload(api_client, auth_headers, tenant_with_case.case_id, content=b"")
    assert status_code == 422


async def test_duplicate_hash_marked_within_same_tenant(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    _, first = await _upload(api_client, auth_headers, tenant_with_case.case_id)
    status_code, second = await _upload(
        api_client, auth_headers, tenant_with_case.case_id, filename="mesmo-print.png"
    )
    assert status_code == 201
    assert second["is_duplicate"] is True
    assert second["duplicate_of_id"] == first["id"]
    # O duplicado ainda assim é um registro e um original independentes.
    assert second["id"] != first["id"]


async def test_same_hash_in_other_tenant_is_not_duplicate(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    other_tenant: TenantFixture,
    storage_root: Path,
) -> None:
    await _upload(api_client, auth_headers, tenant_with_case.case_id)

    other_headers = await login(api_client, other_tenant)
    case_response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, other_headers, urgency="high"),
        headers=other_headers,
    )
    assert case_response.status_code == 201, case_response.text

    status_code, body = await _upload(api_client, other_headers, case_response.json()["id"])
    assert status_code == 201
    # Dedup é por tenant — mesmo conteúdo em outro tenant não é duplicata.
    assert body["is_duplicate"] is False


async def test_other_tenant_cannot_access_evidence(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    other_tenant: TenantFixture,
    storage_root: Path,
) -> None:
    _, created = await _upload(api_client, auth_headers, tenant_with_case.case_id)

    other_headers = await login(api_client, other_tenant)
    base = f"/api/v1/cases/{tenant_with_case.case_id}/evidence"
    for url in (base, f"{base}/{created['id']}", f"{base}/{created['id']}/download"):
        response = await api_client.get(url, headers=other_headers)
        assert response.status_code == 404, url


async def test_viewer_cannot_upload_but_can_read_inventory(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    _, created = await _upload(api_client, auth_headers, tenant_with_case.case_id)

    # Viewer do MESMO tenant: lê o inventário, mas não envia nem baixa o original.
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        session.add(
            User(
                tenant_id=tenant_with_case.tenant_id,
                email="viewer-evidencias@pytestsquad.example.com.br",
                hashed_password=hash_password("senha-de-teste-123"),
                role=UserRole.VIEWER,
            )
        )
        await session.commit()
    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "viewer-evidencias@pytestsquad.example.com.br",
            "password": "senha-de-teste-123",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    base = f"/api/v1/cases/{tenant_with_case.case_id}/evidence"
    status_code, _ = await _upload(api_client, viewer_headers, tenant_with_case.case_id)
    assert status_code == 403

    list_response = await api_client.get(base, headers=viewer_headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    download_response = await api_client.get(
        f"{base}/{created['id']}/download", headers=viewer_headers
    )
    assert download_response.status_code == 403


async def test_download_returns_original_and_audits_access(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    _, created = await _upload(api_client, auth_headers, tenant_with_case.case_id)

    response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{created['id']}/download",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.content == _PNG_BYTES
    assert response.headers["content-type"].startswith("image/png")

    entries = await _audit_entries(tenant_with_case.tenant_id, created["id"])
    actions = [entry.action for entry in entries]
    assert any("anexou" in action for action in actions)  # cadeia de custódia: upload
    assert any("acessou" in action for action in actions)  # cadeia de custódia: download
    assert all(entry.metadata_["entity"] == "evidence" for entry in entries)


async def test_upload_to_missing_case_returns_404(
    api_client: AsyncClient,
    tenant: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,
) -> None:
    status_code, _ = await _upload(api_client, auth_headers, uuid.uuid4())
    assert status_code == 404
