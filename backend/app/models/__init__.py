"""Modelos SQLAlchemy. Importe deste módulo para garantir que todos os
mapeamentos sejam registrados antes de qualquer configuração de relationship.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.case import Case
from app.models.case_checkpoint import CaseCheckpoint
from app.models.case_document import CaseDocument
from app.models.case_intake import CaseIntake
from app.models.catalog import FraudModality, Platform
from app.models.client import Client
from app.models.enums import (
    AuditActor,
    CaseArea,
    CaseStatus,
    DocumentChecklistStatus,
    EvidenceProcessingStatus,
    ExtractionOutcome,
    ExtractionReviewVerdict,
    FraudType,
    MaritalStatus,
    ModuleName,
    PersonType,
    UrgencyLevel,
    UserRole,
)
from app.models.evidence_extraction import EvidenceExtraction, EvidenceExtractionReview
from app.models.evidence_file import EvidenceFile
from app.models.evidence_finding import EvidenceFindingRecord
from app.models.tenant import Tenant
from app.models.tenant_counter import TenantCounter
from app.models.user import User

__all__ = [
    "Base",
    "Tenant",
    "TenantCounter",
    "User",
    "Client",
    "Platform",
    "FraudModality",
    "Case",
    "CaseIntake",
    "CaseDocument",
    "CaseCheckpoint",
    "EvidenceFile",
    "EvidenceExtraction",
    "EvidenceExtractionReview",
    "EvidenceFindingRecord",
    "AuditLog",
    "UserRole",
    "PersonType",
    "MaritalStatus",
    "FraudType",
    "UrgencyLevel",
    "CaseStatus",
    "CaseArea",
    "DocumentChecklistStatus",
    "EvidenceProcessingStatus",
    "ExtractionOutcome",
    "ExtractionReviewVerdict",
    "AuditActor",
    "ModuleName",
]
