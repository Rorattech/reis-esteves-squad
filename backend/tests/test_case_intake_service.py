"""Testes do serviço de relato inicial (app/services/case_intake_service.py)."""

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.db import async_session_factory, scope_session_to_tenant
from app.models.audit_log import AuditLog
from app.models.schemas.case_intake import CaseIntakeCreate, CaseIntakeUpdate
from app.services.case_intake_service import get_intake, submit_intake, update_intake
from tests.conftest import TenantFixture


async def test_submit_intake_creates_record_and_audits(tenant_with_case: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        intake = await submit_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeCreate(
                narrative="Cliente relata golpe do PIX via WhatsApp clonado.",
                estimated_loss_amount=Decimal("5000.00"),
                has_police_report=False,
                claimed_documents=["comprovante_pix.png"],
                pending_information=["boletim_de_ocorrencia"],
            ),
        )

        assert intake is not None
        assert intake.case_id == tenant_with_case.case_id
        assert intake.narrative.startswith("Cliente relata")
        assert intake.claimed_documents == ["comprovante_pix.png"]

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_with_case.tenant_id,
                AuditLog.action == "registrou relato inicial",
            )
        )
        assert audit is not None
        assert audit.case_id == tenant_with_case.case_id
        assert "golpe do PIX" not in audit.input_hash


async def test_submit_intake_returns_none_for_unknown_case(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant.tenant_id)
        result = await submit_intake(
            session,
            tenant_id=tenant.tenant_id,
            case_id=uuid.uuid4(),
            actor_id=tenant.user_id,
            payload=CaseIntakeCreate(narrative="relato qualquer"),
        )
        assert result is None


async def test_submit_intake_is_idempotent_per_case(tenant_with_case: TenantFixture) -> None:
    """Um segundo submit_intake para o mesmo caso substitui o relato, sem duplicar a linha."""
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        first = await submit_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeCreate(narrative="Primeira versão do relato."),
        )
        second = await submit_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeCreate(narrative="Segunda versão do relato."),
        )

        assert first.id == second.id
        assert second.narrative == "Segunda versão do relato."

        audit = await session.scalar(
            select(AuditLog).where(AuditLog.action == "atualizou relato inicial")
        )
        assert audit is not None


async def test_update_intake_patches_only_provided_fields(tenant_with_case: TenantFixture) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        await submit_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeCreate(narrative="Relato original.", has_police_report=False),
        )

        updated = await update_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeUpdate(has_police_report=True),
        )

        assert updated is not None
        assert updated.has_police_report is True
        assert updated.narrative == "Relato original."


async def test_intake_of_one_tenant_is_not_visible_to_another(
    tenant_with_case: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        scope_session_to_tenant(session, tenant_with_case.tenant_id)
        await submit_intake(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseIntakeCreate(narrative="Relato do tenant A."),
        )

    async with async_session_factory() as session:
        scope_session_to_tenant(session, other_tenant.tenant_id)
        result = await get_intake(
            session, tenant_id=other_tenant.tenant_id, case_id=tenant_with_case.case_id
        )
        assert result is None
