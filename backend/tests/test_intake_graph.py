"""Testes dos nós coordinator/triage do módulo Intake (orchestrator/graphs/intake.py).

Cobre os 6 cenários exigidos: golpe PIX, marketplace, fora do escopo digital,
informação insuficiente, isolamento entre tenants e falha de validação de
saída do modelo — sempre com o LLMClient stubado (nunca uma chamada real).
"""

import pytest
from langgraph.runtime import Runtime
from orchestrator.graphs.intake import (
    IntakeContext,
    IntakeValidationError,
    LLMOutputValidationError,
    bootstrap_case,
    build_intake_graph,
    coordinator,
    persist_intake_recommendation,
    triage,
)
from orchestrator.llm import LLMNotConfiguredError
from orchestrator.state import CaseState
from sqlalchemy import select, text

from app.core.db import async_session_factory
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.enums import CaseArea, CaseStatus, FraudType
from tests.conftest import _SET_TENANT_GUC, TenantFixture
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
    "received_documents": ["comprovante_pix.png"],
    "missing_documents": ["boletim_de_ocorrencia"],
    "requires_more_information": False,
    "missing_information": [],
    "rationale": "Faltam apenas o BO para consolidar o conjunto probatório inicial.",
}

_MARKETPLACE_COORDINATOR_RESPONSE = {
    "in_digital_scope": True,
    "platform": "shopee",
    "fraud_type": "marketplace",
    "urgency": "medium",
    "requires_more_information": False,
    "missing_information": [],
    "out_of_scope_reason": None,
    "rationale": "Produto não entregue após 45 dias, vendedor sem resposta.",
}
_MARKETPLACE_TRIAGE_RESPONSE = {
    "area": "digital",
    "matter": "produto não entregue na Shopee",
    "urgency": "medium",
    "case_summary": "Cliente comprou smartphone na Shopee e nunca recebeu o produto.",
    "received_documents": ["print_pedido.png"],
    "missing_documents": ["comprovante_de_endereco"],
    "requires_more_information": False,
    "missing_information": [],
    "rationale": "Endereço de entrega precisa ser confirmado para prosseguir.",
}

_OUT_OF_SCOPE_RESPONSE = {
    "in_digital_scope": False,
    "platform": None,
    "fraud_type": None,
    "urgency": None,
    "requires_more_information": False,
    "missing_information": [],
    "out_of_scope_reason": (
        "Relato descreve disputa de guarda de filhos — Direito de Família, não Digital."
    ),
    "rationale": "Nenhum elemento de golpe digital identificado no relato.",
}

_INSUFFICIENT_INFO_RESPONSE = {
    "in_digital_scope": True,
    "platform": None,
    "fraud_type": None,
    "urgency": None,
    "requires_more_information": True,
    "missing_information": [
        "plataforma envolvida",
        "valor do golpe",
        "data do ocorrido",
    ],
    "out_of_scope_reason": None,
    "rationale": (
        "Relato menciona 'fui enganado on-line' sem detalhes suficientes para classificar."
    ),
}


def _blank_state(*, case_id: str, tenant_id: str, narrative: str = "Relato de teste.") -> CaseState:
    return CaseState(
        case_id=case_id,
        tenant_id=tenant_id,
        narrative=narrative,
        platform="a classificar",
        fraud_type="other",
        urgency="medium",
        area=None,
        matter=None,
        intake_outcome=None,
        missing_information=[],
        out_of_scope_reason=None,
        documents_requested=[],
        evidence_inventory=[],
        legal_sources=[],
        strategy_memo=None,
        draft_petition=None,
        human_approval_required=False,
        human_approval_status="na",
        approved_by=None,
        approved_at=None,
        audit_trail=[],
        current_module="",
        status="active",
    )


def _runtime(stub: StubLLMClient) -> Runtime[IntakeContext]:
    return Runtime(context=IntakeContext(llm_client=stub))


# --- 1. Golpe PIX -----------------------------------------------------------


async def test_pix_case_is_classified_and_reaches_awaiting_human_review() -> None:
    state = _blank_state(
        case_id="caso-pix",
        tenant_id="tenant-1",
        narrative="Recebi mensagem de contato clonado no WhatsApp pedindo PIX de emergência.",
    )
    state.update(bootstrap_case(state))
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])

    coordinator_updates = await coordinator(state, _runtime(stub))
    assert coordinator_updates["intake_outcome"] == "completed"
    assert coordinator_updates["fraud_type"] == "pix"
    assert coordinator_updates["urgency"] == "high"
    state.update(coordinator_updates)

    triage_updates = await triage(state, _runtime(stub))
    assert triage_updates["intake_outcome"] == "awaiting_human_review"
    assert triage_updates["area"] == "digital"
    assert triage_updates["documents_requested"] == ["boletim_de_ocorrencia"]
    assert triage_updates["human_approval_required"] is True
    assert triage_updates["human_approval_status"] == "pending"
    assert len(stub.calls) == 2


async def test_pix_case_full_graph_run_produces_two_audit_entries() -> None:
    state = _blank_state(case_id="caso-pix-graph", tenant_id="tenant-1")
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])
    graph = build_intake_graph()

    result = await graph.ainvoke(state, context=IntakeContext(llm_client=stub))

    assert result["intake_outcome"] == "awaiting_human_review"
    assert result["fraud_type"] == "pix"
    assert result["area"] == "digital"
    # bootstrap_case (system) + coordinator (agent) + triage (agent).
    assert len(result["audit_trail"]) == 3
    assert [entry.actor_id for entry in result["audit_trail"]] == [
        "system",
        "coordinator",
        "triage",
    ]
    coordinator_entry = result["audit_trail"][1]
    assert coordinator_entry.metadata["prompts"][-1]["path"] == "digital/intake/coordinator.md"


# --- 2. Marketplace ----------------------------------------------------------


async def test_marketplace_case_is_classified_and_reaches_awaiting_human_review() -> None:
    state = _blank_state(
        case_id="caso-marketplace",
        tenant_id="tenant-1",
        narrative="Comprei um celular na Shopee há 45 dias e nunca recebi o produto.",
    )
    state.update(bootstrap_case(state))
    stub = StubLLMClient(
        responses=[_MARKETPLACE_COORDINATOR_RESPONSE, _MARKETPLACE_TRIAGE_RESPONSE]
    )

    state.update(await coordinator(state, _runtime(stub)))
    assert state["intake_outcome"] == "completed"
    assert state["fraud_type"] == "marketplace"

    triage_updates = await triage(state, _runtime(stub))
    assert triage_updates["intake_outcome"] == "awaiting_human_review"
    assert triage_updates["matter"] == "produto não entregue na Shopee"
    assert triage_updates["documents_requested"] == ["comprovante_de_endereco"]


# --- 3. Fora do escopo digital -----------------------------------------------


async def test_out_of_scope_case_is_blocked_without_running_triage() -> None:
    state = _blank_state(
        case_id="caso-familia",
        tenant_id="tenant-1",
        narrative="Preciso de ajuda com a guarda dos meus filhos após o divórcio.",
    )
    state.update(bootstrap_case(state))
    stub = StubLLMClient(responses=[_OUT_OF_SCOPE_RESPONSE])

    updates = await coordinator(state, _runtime(stub))

    assert updates["intake_outcome"] == "blocked"
    assert updates["out_of_scope_reason"] is not None
    assert updates["human_approval_required"] is True
    assert updates["human_approval_status"] == "pending"
    assert len(stub.calls) == 1  # triagem nunca deve rodar para caso bloqueado


async def test_out_of_scope_case_graph_run_stops_after_coordinator() -> None:
    state = _blank_state(case_id="caso-familia-graph", tenant_id="tenant-1")
    stub = StubLLMClient(responses=[_OUT_OF_SCOPE_RESPONSE])
    graph = build_intake_graph()

    result = await graph.ainvoke(state, context=IntakeContext(llm_client=stub))

    assert result["intake_outcome"] == "blocked"
    assert result["area"] is None  # triagem não rodou, área nunca é inventada
    assert len(stub.calls) == 1
    assert len(result["audit_trail"]) == 2  # bootstrap_case + coordinator, sem triage


# --- 4. Informações insuficientes --------------------------------------------


async def test_insufficient_information_case_awaits_more_information() -> None:
    state = _blank_state(
        case_id="caso-vago",
        tenant_id="tenant-1",
        narrative="Fui enganado on-line e perdi dinheiro.",
    )
    state.update(bootstrap_case(state))
    stub = StubLLMClient(responses=[_INSUFFICIENT_INFO_RESPONSE])

    updates = await coordinator(state, _runtime(stub))

    assert updates["intake_outcome"] == "awaiting_information"
    assert updates["missing_information"] == [
        "plataforma envolvida",
        "valor do golpe",
        "data do ocorrido",
    ]
    assert updates["human_approval_required"] is True
    assert len(stub.calls) == 1  # triagem não roda sem dados suficientes


# --- 5. Isolamento entre tenants ---------------------------------------------


async def test_persist_intake_recommendation_never_touches_another_tenants_case(
    tenant_with_case: TenantFixture, other_tenant: TenantFixture
) -> None:
    state = _blank_state(
        case_id=str(tenant_with_case.case_id), tenant_id=str(tenant_with_case.tenant_id)
    )
    state.update(
        {
            "platform": "whatsapp",
            "fraud_type": "pix",
            "urgency": "high",
            "area": "digital",
            "matter": "golpe do PIX",
            "intake_outcome": "awaiting_human_review",
        }
    )

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        updated = await persist_intake_recommendation(session, state)
        await session.commit()

        assert updated.tenant_id == tenant_with_case.tenant_id
        assert updated.fraud_type == FraudType.PIX
        assert updated.area == CaseArea.DIGITAL
        assert updated.status == CaseStatus.PENDING_APPROVAL
        assert updated.human_review_required is True

    # O mesmo case_id não pode ser localizado/alterado por outro tenant — a
    # RLS bloqueia a leitura mesmo com case_id correto no state.
    other_state = dict(state)
    other_state["tenant_id"] = str(other_tenant.tenant_id)
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(other_tenant.tenant_id)})
        with pytest.raises(IntakeValidationError):
            await persist_intake_recommendation(session, other_state)

    # O caso original permanece intacto, pertencente ao tenant correto.
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        case = await session.scalar(select(Case).where(Case.id == tenant_with_case.case_id))
        assert case is not None
        assert case.tenant_id == tenant_with_case.tenant_id


async def test_persist_intake_recommendation_persists_and_is_auditable(
    tenant_with_case: TenantFixture,
) -> None:
    """Fim a fim: roda coordinator+triage, persiste no Case e no audit_log,
    tudo escopado ao tenant do caso."""
    state = _blank_state(
        case_id=str(tenant_with_case.case_id), tenant_id=str(tenant_with_case.tenant_id)
    )
    stub = StubLLMClient(responses=[_PIX_COORDINATOR_RESPONSE, _PIX_TRIAGE_RESPONSE])
    graph = build_intake_graph()
    result = await graph.ainvoke(state, context=IntakeContext(llm_client=stub))

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        case = await persist_intake_recommendation(session, result)

        from orchestrator.checkpoints import save_checkpoint

        await save_checkpoint(session, result)
        for entry in result["audit_trail"]:
            from app.core.audit import audit_entry_to_orm

            session.add(
                audit_entry_to_orm(entry, tenant_id=tenant_with_case.tenant_id, case_id=case.id)
            )
        await session.commit()

        stored_logs = (
            await session.scalars(
                select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.created_at)
            )
        ).all()
        assert [log.actor_id for log in stored_logs] == [
            "system",
            "coordinator",
            "triage",
        ]
        assert stored_logs[0].tenant_id == tenant_with_case.tenant_id


# --- 6. Falha de validação de saída do modelo --------------------------------


async def test_coordinator_raises_on_invalid_model_output() -> None:
    state = _blank_state(case_id="caso-invalido", tenant_id="tenant-1")
    state.update(bootstrap_case(state))
    # "in_digital_scope" ausente e "urgency" com valor fora do enum — schema
    # CoordinatorRecommendation deve rejeitar.
    stub = StubLLMClient(
        responses=[{"urgency": "urgentissimo", "rationale": "sem escopo definido"}]
    )

    with pytest.raises(LLMOutputValidationError):
        await coordinator(state, _runtime(stub))


async def test_triage_raises_on_invalid_model_output() -> None:
    state = _blank_state(case_id="caso-invalido-triage", tenant_id="tenant-1")
    state.update(bootstrap_case(state))
    state.update(
        {
            "intake_outcome": "completed",
            "platform": "whatsapp",
            "fraud_type": "pix",
            "urgency": "high",
        }
    )
    # "area" com valor fora do enum CaseArea.
    stub = StubLLMClient(
        responses=[
            {
                "area": "direito-espacial",
                "matter": "x",
                "urgency": "high",
                "case_summary": "y",
                "rationale": "z",
            }
        ]
    )

    with pytest.raises(LLMOutputValidationError):
        await triage(state, _runtime(stub))


def test_llm_not_configured_raises_explicit_error() -> None:
    runtime: Runtime[IntakeContext] = Runtime(context=None)
    from orchestrator.graphs.intake import _require_llm_client

    with pytest.raises(LLMNotConfiguredError):
        _require_llm_client(runtime)


# --- Roteamento (unidade, sem LLM) -------------------------------------------


def test_route_after_coordinator_advances_to_triage_only_when_completed() -> None:
    from langgraph.graph import END
    from orchestrator.graphs.intake import _route_after_coordinator

    state = _blank_state(case_id="c", tenant_id="t")
    state["intake_outcome"] = "completed"
    assert _route_after_coordinator(state) == "triage"

    for outcome in ("blocked", "awaiting_information", None):
        state["intake_outcome"] = outcome
        assert _route_after_coordinator(state) == END
