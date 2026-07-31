"""Testes das rotas de análise de evidências (Fase 3.3 — módulo evidence).

O provedor de IA é sempre um stub injetado via dependency override
(CLAUDE.md, seção 15) — nenhuma chamada de rede real.
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.api.v1.intake import get_llm_client
from app.core.db import async_session_factory
from app.main import app
from tests.conftest import _SET_TENANT_GUC, TenantFixture, login
from tests.llm_stubs import StubLLMClient
from tests.test_evidence_api import _TXT_BYTES, _upload, storage_root  # noqa: F401


def _documental_response(evidence_id: str) -> dict:
    return {
        "items": [
            {
                "evidence_id": evidence_id,
                "evidence_type": "conversation",
                "description": "Conversa exportada com o golpista.",
                "relevance": "high",
                "legal_use": "Comprova a negociação.",
            }
        ],
        "findings": [
            {
                "source_evidence_id": evidence_id,
                "category": "fact",
                "evidence_type": "conversation",
                "summary": "Cliente foi induzido a transferir via PIX.",
                "relevance": "high",
                "suggested_use": "Narrativa dos fatos.",
                "gaps": [],
                "confidence": 0.85,
            },
            {
                "source_evidence_id": None,
                "category": "missing_info",
                "evidence_type": "document",
                "summary": "Falta o comprovante PIX.",
                "relevance": "high",
                "suggested_use": "Solicitar ao cliente.",
                "gaps": ["comprovante PIX"],
                "confidence": 1.0,
            },
        ],
        "missing_documents": ["Comprovante PIX"],
        "rationale": "Inventário do teste.",
    }


_SPECIALIST_RESPONSE = {
    "platform_context": "WhatsApp usado como canal da fraude.",
    "platform_failure": None,
    "report_mechanism_analysis": None,
    "preservation_recommendations": ["Preservar a conversa original no aparelho."],
    "hypotheses": ["Engenharia social com falso vendedor."],
    "findings": [],
    "rationale": "Leitura técnica do teste.",
}


@pytest_asyncio.fixture
async def evidence_ready_case(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> AsyncIterator[tuple[TenantFixture, str]]:
    """Caso no módulo evidence (como após a revisão do Intake) com 1 evidência."""
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="conversa.txt",
        content=_TXT_BYTES,
        mime_type="text/plain",
    )
    async with async_session_factory() as session:
        await session.execute(_SET_TENANT_GUC_TEXT, {"t": str(tenant_with_case.tenant_id)})
        await session.execute(
            text("UPDATE cases SET current_module = 'evidence' WHERE id = :case_id"),
            {"case_id": str(tenant_with_case.case_id)},
        )
        await session.commit()

    stub = StubLLMClient(responses=[_documental_response(body["id"]), _SPECIALIST_RESPONSE])
    app.dependency_overrides[get_llm_client] = lambda: stub
    try:
        yield tenant_with_case, body["id"]
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


_SET_TENANT_GUC_TEXT = text(_SET_TENANT_GUC)


async def test_run_analysis_persists_findings_and_requires_review(
    api_client: AsyncClient,
    evidence_ready_case: tuple[TenantFixture, str],
    auth_headers: dict[str, str],
) -> None:
    tenant, evidence_id = evidence_ready_case
    base = f"/api/v1/cases/{tenant.case_id}/evidence/analysis"

    response = await api_client.post(f"{base}/run", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["evidence_outcome"] == "awaiting_human_review"
    assert body["human_review_required"] is True
    assert body["status"] == "pending_approval"
    assert body["current_module"] == "evidence"
    assert body["specialist_assessment"]["status"] == "DRAFT_PENDING_REVIEW"
    assert "Comprovante PIX" in body["documents_requested"]

    findings = body["findings"]
    assert len(findings) == 2
    assert all(f["status"] == "DRAFT_PENDING_REVIEW" for f in findings)
    fact = next(f for f in findings if f["category"] == "fact")
    assert fact["evidence_id"] == evidence_id  # rastreável até a evidência original
    gap = next(f for f in findings if f["category"] == "missing_info")
    assert gap["evidence_id"] is None

    # GET result devolve o mesmo estado consolidado.
    result = await api_client.get(f"{base}/result", headers=auth_headers)
    assert result.status_code == 200
    assert len(result.json()["findings"]) == 2


async def test_review_approve_advances_case_to_research(
    api_client: AsyncClient,
    evidence_ready_case: tuple[TenantFixture, str],
    auth_headers: dict[str, str],
) -> None:
    tenant, _ = evidence_ready_case
    base = f"/api/v1/cases/{tenant.case_id}/evidence/analysis"
    await api_client.post(f"{base}/run", headers=auth_headers)

    response = await api_client.post(
        f"{base}/review", json={"decision": "approve"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_module"] == "research"
    assert body["human_review_required"] is False
    assert all(f["status"] == "APPROVED" for f in body["findings"])

    # Revisar de novo sem nova análise pendente é conflito.
    again = await api_client.post(
        f"{base}/review", json={"decision": "approve"}, headers=auth_headers
    )
    assert again.status_code == 409


async def test_review_return_keeps_case_in_evidence(
    api_client: AsyncClient,
    evidence_ready_case: tuple[TenantFixture, str],
    auth_headers: dict[str, str],
) -> None:
    tenant, _ = evidence_ready_case
    base = f"/api/v1/cases/{tenant.case_id}/evidence/analysis"
    await api_client.post(f"{base}/run", headers=auth_headers)

    response = await api_client.post(
        f"{base}/review",
        json={"decision": "return_for_information", "notes": "Falta o comprovante PIX."},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_module"] == "evidence"
    assert body["human_review_required"] is True
    # Devolver não aprova nada: os achados continuam pendentes.
    assert all(f["status"] == "DRAFT_PENDING_REVIEW" for f in body["findings"])


async def test_run_rejected_while_case_still_in_intake(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    stub = StubLLMClient(responses=[])
    app.dependency_overrides[get_llm_client] = lambda: stub
    try:
        response = await api_client.post(
            f"/api/v1/cases/{tenant_with_case.case_id}/evidence/analysis/run",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
    assert response.status_code == 422
    assert "triagem" in response.json()["detail"]


async def test_analysis_is_tenant_isolated(
    api_client: AsyncClient,
    evidence_ready_case: tuple[TenantFixture, str],
    auth_headers: dict[str, str],
    other_tenant: TenantFixture,
) -> None:
    tenant, _ = evidence_ready_case
    base = f"/api/v1/cases/{tenant.case_id}/evidence/analysis"
    await api_client.post(f"{base}/run", headers=auth_headers)

    other_headers = await login(api_client, other_tenant)
    for method, url in (
        ("POST", f"{base}/run"),
        ("GET", f"{base}/result"),
        ("POST", f"{base}/review"),
    ):
        kwargs = {"headers": other_headers}
        if url.endswith("review"):
            kwargs["json"] = {"decision": "approve"}
        response = await api_client.request(method, url, **kwargs)
        assert response.status_code == 404, url


async def test_result_404_before_first_run(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
) -> None:
    response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/analysis/result",
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_viewer_cannot_run_analysis(
    api_client: AsyncClient, viewer_tenant: TenantFixture
) -> None:
    headers = await login(api_client, viewer_tenant)
    response = await api_client.post(
        f"/api/v1/cases/{uuid.uuid4()}/evidence/analysis/run", headers=headers
    )
    assert response.status_code == 403
