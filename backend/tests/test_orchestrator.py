"""Testes do esqueleto do orquestrador: grafo Intake, router e checkpoints
(docs/architecture.md, seção 3.3; CLAUDE.md, seção 14)."""

import uuid

import pytest
from sqlalchemy import text

from app.core.db import async_session_factory
from app.models.case import Case
from app.models.enums import FraudType, UrgencyLevel
from orchestrator.checkpoints import load_latest_checkpoint, save_checkpoint
from orchestrator.graphs.intake import IntakeValidationError, bootstrap_case, build_intake_graph
from orchestrator.router import route
from orchestrator.state import CaseState
from tests.conftest import _SET_TENANT_GUC, TenantFixture


def _blank_state(*, case_id: str, tenant_id: str) -> CaseState:
    return CaseState(
        case_id=case_id,
        tenant_id=tenant_id,
        platform="whatsapp",
        fraud_type="pix",
        urgency="high",
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


def test_bootstrap_case_raises_on_missing_required_fields() -> None:
    incomplete_state = _blank_state(case_id="", tenant_id="algum-tenant")
    with pytest.raises(IntakeValidationError):
        bootstrap_case(incomplete_state)


def test_bootstrap_case_sets_module_and_appends_audit_entry() -> None:
    state = _blank_state(case_id="caso-1", tenant_id="tenant-1")
    updates = bootstrap_case(state)

    assert updates["current_module"] == "intake"
    assert updates["status"] == "active"
    assert len(updates["audit_trail"]) == 1
    assert updates["audit_trail"][0].actor == "system"


async def test_intake_graph_invoke_runs_bootstrap_node() -> None:
    state = _blank_state(case_id="caso-2", tenant_id="tenant-2")
    graph = build_intake_graph()

    result = await graph.ainvoke(state)

    assert result["current_module"] == "intake"
    assert len(result["audit_trail"]) == 1


def test_router_advances_to_next_module_when_active() -> None:
    state = _blank_state(case_id="c", tenant_id="t")
    state["current_module"] = "intake"
    state["status"] = "active"
    assert route(state) == "evidence"


def test_router_does_not_advance_review_module() -> None:
    state = _blank_state(case_id="c", tenant_id="t")
    state["current_module"] = "review"
    state["status"] = "active"
    assert route(state) is None


def test_router_does_not_advance_when_awaiting_human_approval() -> None:
    state = _blank_state(case_id="c", tenant_id="t")
    state["current_module"] = "strategy"
    state["status"] = "active"
    state["human_approval_required"] = True
    state["human_approval_status"] = "pending"
    assert route(state) is None


def test_router_does_not_advance_suspended_or_completed_case() -> None:
    for terminal_status in ("suspended", "completed", "error"):
        state = _blank_state(case_id="c", tenant_id="t")
        state["current_module"] = "intake"
        state["status"] = terminal_status
        assert route(state) is None


async def test_checkpoint_round_trip_preserves_case_state(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        case = Case(
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            platform="whatsapp",
            fraud_type=FraudType.PIX,
            urgency=UrgencyLevel.HIGH,
        )
        session.add(case)
        await session.flush()

        state = _blank_state(case_id=str(case.id), tenant_id=str(tenant.tenant_id))
        state.update(bootstrap_case(state))

        first_checkpoint = await save_checkpoint(session, state)
        assert first_checkpoint.step == 1

        second_checkpoint = await save_checkpoint(session, state)
        assert second_checkpoint.step == 2
        await session.commit()

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        loaded = await load_latest_checkpoint(session, tenant_id=tenant.tenant_id, case_id=case.id)

        assert loaded is not None
        assert loaded["current_module"] == "intake"
        assert len(loaded["audit_trail"]) == 1
        assert loaded["audit_trail"][0].action == state["audit_trail"][0].action


async def test_load_latest_checkpoint_returns_none_when_absent(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        result = await load_latest_checkpoint(
            session, tenant_id=tenant.tenant_id, case_id=uuid.uuid4()
        )
        assert result is None
