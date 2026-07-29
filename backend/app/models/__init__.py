"""Modelos SQLAlchemy. Importe deste módulo para garantir que todos os
mapeamentos sejam registrados antes de qualquer configuração de relationship.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.case import Case
from app.models.case_checkpoint import CaseCheckpoint
from app.models.enums import (
    AuditActor,
    CaseStatus,
    FraudType,
    ModuleName,
    UrgencyLevel,
    UserRole,
)
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "Base",
    "Tenant",
    "User",
    "Case",
    "CaseCheckpoint",
    "AuditLog",
    "UserRole",
    "FraudType",
    "UrgencyLevel",
    "CaseStatus",
    "AuditActor",
    "ModuleName",
]
