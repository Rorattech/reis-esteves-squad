"""Testes do serviço de checklist de documentos (app/services/case_document_service.py)."""

import uuid

from sqlalchemy import select, text

from app.core.db import async_session_factory
from app.models.audit_log import AuditLog
from app.models.enums import DocumentChecklistStatus
from app.models.schemas.case_document import CaseDocumentCreate, CaseDocumentUpdate
from app.services.case_document_service import (
    add_checklist_item,
    list_checklist,
    update_checklist_item,
)
from tests.conftest import _SET_TENANT_GUC, TenantFixture


async def test_add_checklist_item_persists_and_audits(tenant_with_case: TenantFixture) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        item = await add_checklist_item(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseDocumentCreate(name="Boletim de Ocorrência"),
        )

        assert item is not None
        assert item.status == DocumentChecklistStatus.PENDING
        assert item.origin == "intake"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_with_case.tenant_id,
                AuditLog.action == "adicionou item ao checklist de documentos",
            )
        )
        assert audit is not None
        assert audit.case_id == tenant_with_case.case_id


async def test_add_checklist_item_returns_none_for_unknown_case(tenant: TenantFixture) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant.tenant_id)})
        result = await add_checklist_item(
            session,
            tenant_id=tenant.tenant_id,
            case_id=uuid.uuid4(),
            actor_id=tenant.user_id,
            payload=CaseDocumentCreate(name="Comprovante PIX"),
        )
        assert result is None


async def test_duplicate_checklist_item_name_is_rejected(tenant_with_case: TenantFixture) -> None:
    from sqlalchemy.exc import IntegrityError

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        await add_checklist_item(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseDocumentCreate(name="Comprovante PIX"),
        )

        try:
            await add_checklist_item(
                session,
                tenant_id=tenant_with_case.tenant_id,
                case_id=tenant_with_case.case_id,
                actor_id=tenant_with_case.user_id,
                payload=CaseDocumentCreate(name="Comprovante PIX"),
            )
            raised = False
        except IntegrityError:
            raised = True
            await session.rollback()
        assert raised


async def test_update_checklist_item_changes_status(tenant_with_case: TenantFixture) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        item = await add_checklist_item(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseDocumentCreate(name="URL do perfil falso"),
        )

        updated = await update_checklist_item(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            document_id=item.id,
            actor_id=tenant_with_case.user_id,
            payload=CaseDocumentUpdate(status=DocumentChecklistStatus.RECEIVED),
        )

        assert updated is not None
        assert updated.status == DocumentChecklistStatus.RECEIVED


async def test_checklist_of_one_tenant_is_not_visible_to_another(
    tenant_with_case: TenantFixture, other_tenant: TenantFixture
) -> None:
    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        await add_checklist_item(
            session,
            tenant_id=tenant_with_case.tenant_id,
            case_id=tenant_with_case.case_id,
            actor_id=tenant_with_case.user_id,
            payload=CaseDocumentCreate(name="Print da conversa"),
        )

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(other_tenant.tenant_id)})
        items = await list_checklist(
            session, tenant_id=other_tenant.tenant_id, case_id=tenant_with_case.case_id
        )
        assert items == []
