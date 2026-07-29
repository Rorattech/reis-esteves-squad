"""Testes de backend/app/core/audit.py (CLAUDE.md, seção 10)."""

import uuid

from sqlalchemy import select, text

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.db import async_session_factory
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.enums import AuditActor, FraudType, ModuleName, UrgencyLevel
from tests.conftest import _SET_TENANT_GUC, TenantFixture


def test_create_audit_entry_hashes_input_and_output_never_stores_raw_content() -> None:
    entry = create_audit_entry(
        actor_id="coordinator",
        action="classificou a plataforma ré",
        module="intake",
        input_data={"relato": "cliente perdeu R$ 5000 em golpe do PIX"},
        output_data={"platform": "whatsapp", "fraud_type": "pix"},
        model_used="claude-sonnet-5",
        tokens_used=512,
        duration_ms=340,
    )

    assert entry.actor == "agent"
    assert entry.actor_id == "coordinator"
    assert entry.module == "intake"
    assert len(entry.input_hash) == 64
    assert len(entry.output_hash) == 64
    # nenhum dado bruto (CPF, relato do cliente etc.) deve sobreviver no objeto.
    assert "5000" not in entry.model_dump_json()
    assert "cliente" not in entry.model_dump_json()


def test_create_audit_entry_is_deterministic_for_same_input() -> None:
    kwargs = dict(
        actor_id="triage",
        action="mesma acao",
        module="intake",
        input_data={"a": 1, "b": 2},
        output_data={"c": 3},
        model_used="claude-sonnet-5",
        tokens_used=10,
        duration_ms=5,
    )
    first = create_audit_entry(**kwargs)
    second = create_audit_entry(**kwargs)
    assert first.input_hash == second.input_hash
    assert first.output_hash == second.output_hash


def test_audit_entry_to_orm_maps_fields_correctly() -> None:
    entry = create_audit_entry(
        actor_id="specialist",
        action="analisou evidencia tecnica",
        module="evidence",
        input_data={"x": 1},
        output_data={"y": 2},
        model_used="claude-sonnet-5",
        tokens_used=77,
        duration_ms=120,
        actor="agent",
        metadata={"confidence": 0.9},
    )
    tenant_id = uuid.uuid4()
    case_id = uuid.uuid4()

    orm = audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id)

    assert orm.tenant_id == tenant_id
    assert orm.case_id == case_id
    assert orm.actor == AuditActor.AGENT
    assert orm.module == ModuleName.EVIDENCE
    assert orm.agent_name == "specialist"
    assert orm.tokens_used == 77
    assert orm.duration_ms == 120
    assert orm.metadata_ == {"confidence": 0.9}


async def test_audit_entry_persists_to_audit_logs_table(tenant: TenantFixture) -> None:
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

        entry = create_audit_entry(
            actor_id="coordinator",
            action="validou o caso",
            module="intake",
            input_data={"platform": "whatsapp"},
            output_data={"status": "active"},
            model_used="n/a",
            tokens_used=0,
            duration_ms=1,
            actor="system",
        )
        orm_entry = audit_entry_to_orm(entry, tenant_id=tenant.tenant_id, case_id=case.id)
        session.add(orm_entry)
        await session.commit()

        stored = await session.scalar(select(AuditLog).where(AuditLog.case_id == case.id))
        assert stored is not None
        assert stored.action == "validou o caso"
        assert stored.actor == AuditActor.SYSTEM
