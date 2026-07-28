"""Enums compartilhados pelos modelos SQLAlchemy (mapeados como ENUM nativo do Postgres)."""

import enum


class UserRole(str, enum.Enum):
    """Papéis RBAC do usuário dentro do tenant (ver CLAUDE.md, seção 12)."""

    ADMIN = "admin"
    LAWYER = "lawyer"
    PARALEGAL = "paralegal"
    VIEWER = "viewer"


class FraudType(str, enum.Enum):
    """Modalidade do golpe identificada no módulo de Intake (ver docs/architecture.md)."""

    PIX = "pix"
    MARKETPLACE = "marketplace"
    FAKE_PROFILE = "fake_profile"
    FAKE_LAWYER = "fake_lawyer"
    OTHER = "other"


class UrgencyLevel(str, enum.Enum):
    """Urgência do caso, usada para avaliar necessidade de tutela de urgência."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CaseStatus(str, enum.Enum):
    """Status do caso ao longo do fluxo human-in-the-loop dos módulos LangGraph."""

    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    ARCHIVED = "archived"
