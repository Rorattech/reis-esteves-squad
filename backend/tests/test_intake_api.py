"""Testes da API de Intake e revisão humana (Fase 2.4 — app/api/v1/intake.py).

Cobre autenticação, RBAC, isolamento de tenants e o fluxo de revisão humana
— sempre com o LLMClient stubado via app.dependency_overrides (nunca uma
chamada real, ver app/api/v1/intake.py::get_llm_client).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import AsyncClient

from app.api.v1.intake import get_llm_client
from app.core.db import async_session_factory, scope_session_to_tenant
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import TenantFixture, case_payload, login
from tests.llm_stubs import StubLLMClient

_PIX_COORDINATOR_RESPONSE = {
    "in_digital_scope": True,
    "platform": "whatsapp",
    "fraud_type": "pix",
    "urgency": "high",
    "requires_more_information": False,
    "missing_information": [],
    "out_of_scope_reason": None,
    "rationale": "Cliente relata PIX enviado a golpista via contato clonado no WhatsApp.",
}
_PIX_TRIAGE_RESPONSE = {
    "area": "digital",
    "matter": "golpe do PIX via WhatsApp clonado",
    "urgency": "high",
    "case_summary": "Cliente transferiu R$ 3.000 via PIX após contato de número clonado.",
    "received_documents": [],
    "missing_documents": ["boletim_de_ocorrencia"],
    "requires_more_information": False,
    "missing_information": [],
    "rationale": "Faltam apenas o BO para consolidar o conjunto probatório inicial.",
}


@asynccontextmanager
async def _llm_client_override(stub: StubLLMClient) -> AsyncIterator[None]:
    app.dependency_overrides[get_llm_client] = lambda: stub
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


async def _login_as_new_user(
    api_client: AsyncClient, tenant: TenantFixture, role: UserRole
) -> dict[str, str]:
    """Cria um usuário adicional com `role` no mesmo tenant de `tenant` e faz login."""
    email = f"user-{uuid.uuid4().hex[:10]}@pytestsquad.example.com.br"
    password = "senha-de-teste-123"
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        session.add(
            User(
                tenant_id=tenant.tenant_id,
                email=email,
                hashed_password=hash_password(password),
                role=role,
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _run_intake(api_client: AsyncClient, case_id: str, headers: dict[str, str]):
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])
    async with _llm_client_override(stub):
        return await api_client.post(f"/api/v1/cases/{case_id}/intake/run", headers=headers)


# --- Autenticação -------------------------------------------------------------


async def test_intake_endpoints_require_authentication(api_client: AsyncClient) -> None:
    case_id = uuid.uuid4()
    endpoints = [
        ("post", f"/api/v1/cases/{case_id}/intake", {"narrative": "x"}),
        ("get", f"/api/v1/cases/{case_id}/intake", None),
        ("post", f"/api/v1/cases/{case_id}/documents", {"name": "x"}),
        ("get", f"/api/v1/cases/{case_id}/documents", None),
        ("post", f"/api/v1/cases/{case_id}/intake/run", None),
        ("get", f"/api/v1/cases/{case_id}/intake/result", None),
        ("post", f"/api/v1/cases/{case_id}/intake/review", {"decision": "approve"}),
        ("get", f"/api/v1/cases/{case_id}/audit-log", None),
    ]
    for method, path, payload in endpoints:
        response = await api_client.request(method.upper(), path, json=payload)
        assert response.status_code == 403, f"{method.upper()} {path} deveria exigir autenticação"


# --- Fluxo completo (criação -> relato -> checklist -> run -> review -> auditoria) --


async def test_full_intake_flow(api_client: AsyncClient, tenant: TenantFixture) -> None:
    headers = await login(api_client, tenant)

    create_response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, urgency="high"),
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    case_id = create_response.json()["id"]

    intake_response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake",
        json={"narrative": "Recebi mensagem de contato clonado no WhatsApp pedindo PIX urgente."},
        headers=headers,
    )
    assert intake_response.status_code == 201, intake_response.text

    doc_response = await api_client.post(
        f"/api/v1/cases/{case_id}/documents",
        json={"name": "Comprovante PIX"},
        headers=headers,
    )
    assert doc_response.status_code == 201, doc_response.text

    list_docs_response = await api_client.get(f"/api/v1/cases/{case_id}/documents", headers=headers)
    assert list_docs_response.status_code == 200
    assert len(list_docs_response.json()) == 1

    run_response = await _run_intake(api_client, case_id, headers)
    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    assert run_body["intake_outcome"] == "awaiting_human_review"
    assert run_body["area"] == "digital"
    assert run_body["human_review_required"] is True
    assert run_body["status"] == "pending_approval"
    assert run_body["documents_requested"] == ["boletim_de_ocorrencia"]

    result_response = await api_client.get(
        f"/api/v1/cases/{case_id}/intake/result", headers=headers
    )
    assert result_response.status_code == 200
    assert result_response.json() == run_body

    review_response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert review_response.status_code == 200, review_response.text
    reviewed_case = review_response.json()
    assert reviewed_case["human_review_required"] is False
    assert reviewed_case["current_module"] == "evidence"
    assert reviewed_case["status"] == "in_progress"

    audit_response = await api_client.get(f"/api/v1/cases/{case_id}/audit-log", headers=headers)
    assert audit_response.status_code == 200
    actions = [entry["action"] for entry in audit_response.json()]
    assert "revisão humana do intake: approve" in actions
    actor_ids = [entry["actor_id"] for entry in audit_response.json()]
    assert "coordinator" in actor_ids
    assert "triage" in actor_ids


async def test_review_correction_applies_fields_and_advances_case(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    headers = await login(api_client, tenant)
    create_response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, urgency="medium"),
        headers=headers,
    )
    case_id = create_response.json()["id"]
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake",
        json={"narrative": "Comprei um produto e nunca recebi."},
        headers=headers,
    )
    await _run_intake(api_client, case_id, headers)

    review_response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={
            "decision": "correct",
            "notes": "Advogado ajustou a matéria após conferir o relato.",
            "matter": "produto não entregue — golpe marketplace confirmado",
        },
        headers=headers,
    )
    assert review_response.status_code == 200, review_response.text
    body = review_response.json()
    assert body["matter"] == "produto não entregue — golpe marketplace confirmado"
    assert body["current_module"] == "evidence"


async def test_review_return_for_information_keeps_case_in_intake(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    headers = await login(api_client, tenant)
    create_response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, urgency="high"),
        headers=headers,
    )
    case_id = create_response.json()["id"]
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake",
        json={"narrative": "relato inicial"},
        headers=headers,
    )
    await _run_intake(api_client, case_id, headers)

    review_response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={
            "decision": "return_for_information",
            "notes": "Faltou o valor do golpe.",
        },
        headers=headers,
    )
    assert review_response.status_code == 200, review_response.text
    body = review_response.json()
    assert body["current_module"] == "intake"
    assert body["human_review_required"] is True


async def test_review_requires_notes_for_non_approval_decisions(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/review",
        json={"decision": "correct"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_review_without_pending_recommendation_is_conflict(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert response.status_code == 409


async def test_reviewing_twice_after_approval_is_conflict(
    api_client: AsyncClient, tenant: TenantFixture
) -> None:
    headers = await login(api_client, tenant)
    create_response = await api_client.post(
        "/api/v1/cases",
        json=await case_payload(api_client, headers, urgency="high"),
        headers=headers,
    )
    case_id = create_response.json()["id"]
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake", json={"narrative": "relato"}, headers=headers
    )
    await _run_intake(api_client, case_id, headers)
    first = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert first.status_code == 200

    second = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert second.status_code == 409


# --- Avanço manual da abertura do caso para Evidências ------------------------


async def test_advance_moves_case_to_evidence_without_ai_triage(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    """Sem provedor de IA, a triagem responde 503 e o caso nunca chega a
    pending_approval — o avanço manual é o único caminho para Evidências."""
    headers = await login(api_client, tenant_with_case)
    case_id = tenant_with_case.case_id
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake",
        json={"narrative": "Comprei um celular e nunca recebi."},
        headers=headers,
    )

    blocked = await api_client.post(f"/api/v1/cases/{case_id}/intake/run", headers=headers)
    assert blocked.status_code == 503
    conflict = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert conflict.status_code == 409

    response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/advance",
        json={"notes": "Relato e documentos conferidos manualmente."},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_module"] == "evidence"
    assert body["status"] == "in_progress"


async def test_advance_is_recorded_in_the_audit_log_as_a_human_action(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    case_id = tenant_with_case.case_id
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake", json={"narrative": "relato"}, headers=headers
    )
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake/advance",
        json={"notes": "abertura concluída"},
        headers=headers,
    )

    audit = await api_client.get(f"/api/v1/cases/{case_id}/audit-log", headers=headers)
    entries = [e for e in audit.json() if "avanço manual" in e["action"]]
    assert len(entries) == 1
    assert entries[0]["actor"] == "human"
    assert entries[0]["metadata"]["notes"] == "abertura concluída"
    # Deixa explícito no histórico que nenhuma recomendação de IA foi revisada.
    assert entries[0]["metadata"]["ai_triage_reviewed"] is False


async def test_advance_without_narrative_returns_422(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/advance",
        json={},
        headers=headers,
    )
    assert response.status_code == 422


async def test_advance_twice_is_conflict(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    case_id = tenant_with_case.case_id
    await api_client.post(
        f"/api/v1/cases/{case_id}/intake", json={"narrative": "relato"}, headers=headers
    )
    first = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/advance", json={}, headers=headers
    )
    assert first.status_code == 200

    second = await api_client.post(
        f"/api/v1/cases/{case_id}/intake/advance", json={}, headers=headers
    )
    assert second.status_code == 409


async def test_viewer_cannot_advance_case(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    owner_headers = await login(api_client, tenant_with_case)
    await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "relato"},
        headers=owner_headers,
    )
    viewer_headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/advance",
        json={},
        headers=viewer_headers,
    )
    assert response.status_code == 403


async def test_advance_is_isolated_between_tenants(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    other_tenant: TenantFixture,
) -> None:
    owner_headers = await login(api_client, tenant_with_case)
    await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "relato"},
        headers=owner_headers,
    )
    intruder_headers = await login(api_client, other_tenant)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/advance",
        json={},
        headers=intruder_headers,
    )
    assert response.status_code == 404


# --- Execução sem provedor de IA configurado / sem relato --------------------


async def test_run_intake_without_llm_provider_returns_503(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "relato"},
        headers=headers,
    )
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/run", headers=headers
    )
    assert response.status_code == 503


async def test_run_intake_without_narrative_returns_422(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])
    async with _llm_client_override(stub):
        response = await api_client.post(
            f"/api/v1/cases/{tenant_with_case.case_id}/intake/run", headers=headers
        )
    assert response.status_code == 422


async def test_get_intake_result_before_run_returns_404(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await login(api_client, tenant_with_case)
    response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/result", headers=headers
    )
    assert response.status_code == 404


# --- RBAC -----------------------------------------------------------------------


async def test_viewer_cannot_submit_intake(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "x"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_viewer_cannot_add_document(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/documents",
        json={"name": "x"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_viewer_cannot_run_intake(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/run", headers=headers
    )
    assert response.status_code == 403


async def test_viewer_cannot_review_intake(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_viewer_cannot_read_audit_log(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/audit-log", headers=headers
    )
    assert response.status_code == 403


async def test_viewer_can_read_checklist_and_intake_narrative(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    admin_headers = await login(api_client, tenant_with_case)
    await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "relato visível para leitura"},
        headers=admin_headers,
    )

    viewer_headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.VIEWER)
    intake_response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake", headers=viewer_headers
    )
    assert intake_response.status_code == 200

    docs_response = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/documents", headers=viewer_headers
    )
    assert docs_response.status_code == 200


async def test_paralegal_can_submit_intake_and_add_documents(
    api_client: AsyncClient, tenant_with_case: TenantFixture
) -> None:
    headers = await _login_as_new_user(api_client, tenant_with_case, UserRole.PARALEGAL)
    intake_response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/intake",
        json={"narrative": "relato registrado por paralegal"},
        headers=headers,
    )
    assert intake_response.status_code == 201

    doc_response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/documents",
        json={"name": "Documento X"},
        headers=headers,
    )
    assert doc_response.status_code == 201


# --- Isolamento entre tenants -----------------------------------------------


async def test_intake_endpoints_are_isolated_between_tenants(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    other_tenant: TenantFixture,
) -> None:
    headers_a = await login(api_client, tenant_with_case)
    headers_b = await login(api_client, other_tenant)
    case_id = tenant_with_case.case_id

    # Tenant B nunca enxerga nem consegue mutar o caso do tenant A. /intake/run
    # roda sob um LLMClient stubado: sem isso, a dependency get_llm_client
    # sempre devolveria 503 antes mesmo de checar o tenant (ver
    # test_run_intake_without_llm_provider_returns_503), mascarando o que
    # este teste quer provar — isolamento, não disponibilidade do provedor.
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])
    async with _llm_client_override(stub):
        for method, path, payload in [
            ("post", f"/api/v1/cases/{case_id}/intake", {"narrative": "invasao"}),
            ("get", f"/api/v1/cases/{case_id}/intake", None),
            ("post", f"/api/v1/cases/{case_id}/documents", {"name": "x"}),
            ("get", f"/api/v1/cases/{case_id}/documents", None),
            ("post", f"/api/v1/cases/{case_id}/intake/run", None),
            ("get", f"/api/v1/cases/{case_id}/intake/result", None),
            ("post", f"/api/v1/cases/{case_id}/intake/review", {"decision": "approve"}),
            ("get", f"/api/v1/cases/{case_id}/audit-log", None),
        ]:
            response = await api_client.request(
                method.upper(), path, json=payload, headers=headers_b
            )
            assert response.status_code == 404, f"{method.upper()} {path} vazou entre tenants"

    # Tenant A (dono do caso) continua operando normalmente.
    own_response = await api_client.post(
        f"/api/v1/cases/{case_id}/intake",
        json={"narrative": "relato legítimo do dono do caso"},
        headers=headers_a,
    )
    assert own_response.status_code == 201

    # E o tenant B ainda não vê o relato que acabou de ser criado no tenant A.
    still_hidden = await api_client.get(f"/api/v1/cases/{case_id}/intake", headers=headers_b)
    assert still_hidden.status_code == 404


async def test_document_checklist_item_is_isolated_between_tenants(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    other_tenant: TenantFixture,
) -> None:
    headers_a = await login(api_client, tenant_with_case)
    headers_b = await login(api_client, other_tenant)

    doc_response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/documents",
        json={"name": "Comprovante"},
        headers=headers_a,
    )
    document_id = doc_response.json()["id"]

    response = await api_client.patch(
        f"/api/v1/cases/{tenant_with_case.case_id}/documents/{document_id}",
        json={"status": "received"},
        headers=headers_b,
    )
    assert response.status_code == 404
