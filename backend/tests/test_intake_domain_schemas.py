"""Testes de validação dos schemas Pydantic da Fase 2 — Intake e Roteamento."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.enums import CaseArea, DocumentChecklistStatus, FraudType
from app.models.schemas.case import CaseCreate
from app.models.schemas.case_document import CaseDocumentCreate
from app.models.schemas.case_intake import CaseIntakeCreate
from app.models.schemas.client import ClientCreate


def test_client_create_rejects_empty_full_name() -> None:
    with pytest.raises(ValidationError):
        ClientCreate(full_name="")


def test_client_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        ClientCreate(full_name="Cliente Válido", email="nao-e-um-email")


def test_client_create_accepts_minimal_payload() -> None:
    client = ClientCreate(full_name="Cliente Mínimo")
    assert client.document_number is None
    assert client.email is None


def test_case_intake_create_rejects_empty_narrative() -> None:
    with pytest.raises(ValidationError):
        CaseIntakeCreate(narrative="")


def test_case_intake_create_rejects_negative_loss_amount() -> None:
    with pytest.raises(ValidationError):
        CaseIntakeCreate(narrative="relato válido", estimated_loss_amount=Decimal("-1"))


def test_case_intake_create_accepts_valid_payload() -> None:
    intake = CaseIntakeCreate(
        narrative="Cliente perdeu dinheiro em golpe do Marketplace.",
        estimated_loss_amount=Decimal("1200.50"),
        has_police_report=True,
        claimed_documents=["nota_fiscal.pdf"],
    )
    assert intake.claimed_documents == ["nota_fiscal.pdf"]
    assert intake.pending_information == []


def test_case_document_create_defaults_to_pending_status() -> None:
    document = CaseDocumentCreate(name="Comprovante de pagamento")
    assert document.status == DocumentChecklistStatus.PENDING
    assert document.origin == "intake"


def test_case_document_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        CaseDocumentCreate(name="")


def test_case_document_create_accepts_explicit_status() -> None:
    document = CaseDocumentCreate(name="RG do cliente", status=DocumentChecklistStatus.WAIVED)
    assert document.status == DocumentChecklistStatus.WAIVED


def test_case_create_accepts_optional_area_and_matter() -> None:
    case = CaseCreate(
        platform="shopee",
        fraud_type=FraudType.MARKETPLACE,
        area=CaseArea.DIGITAL,
        matter="golpe marketplace",
    )
    assert case.area == CaseArea.DIGITAL
    assert case.client_id is None


def test_case_create_rejects_invalid_area() -> None:
    with pytest.raises(ValidationError):
        CaseCreate(platform="shopee", fraud_type=FraudType.MARKETPLACE, area="nao-existe")
