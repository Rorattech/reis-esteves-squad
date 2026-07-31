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


class AuditActor(str, enum.Enum):
    """Quem executou a ação registrada em AuditLog (espelha ActorType em
    orchestrator/state.py — CLAUDE.md, seção 10).
    """

    SYSTEM = "system"
    AGENT = "agent"
    HUMAN = "human"


class ModuleName(str, enum.Enum):
    """Um dos 6 módulos LangGraph do Squad Digital (espelha ModuleName em
    orchestrator/state.py — CLAUDE.md, seção 14).
    """

    INTAKE = "intake"
    EVIDENCE = "evidence"
    RESEARCH = "research"
    STRATEGY = "strategy"
    DRAFTING = "drafting"
    REVIEW = "review"


class CaseArea(str, enum.Enum):
    """Área do Direito identificada no módulo de Triagem (ver
    prompts/digital/intake/triage.md — Digital = Meta/Facebook/Marketplace/
    Shopee/Mercado Livre/WhatsApp/falso advogado/golpe PIX).
    """

    CIVIL = "civil"
    FAMILY = "family"
    CRIMINAL = "criminal"
    LABOR = "labor"
    CONSUMER = "consumer"
    DIGITAL = "digital"


class DocumentChecklistStatus(str, enum.Enum):
    """Status de um item do checklist de documentos de um caso."""

    RECEIVED = "received"
    PENDING = "pending"
    WAIVED = "waived"


class EvidenceProcessingStatus(str, enum.Enum):
    """Status de processamento de um arquivo de evidência (Fase 3 — módulo evidence).

    received: upload concluído, ainda sem extração de conteúdo (Fase 3.2).
    processing: pipeline de OCR/transcrição em execução.
    processed: extração concluída (com sucesso ou com baixa confiança sinalizada).
    failed: pipeline de extração falhou — arquivo original permanece intacto.
    """

    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ExtractionOutcome(str, enum.Enum):
    """Resultado de uma execução do pipeline de extração (Fase 3.2).

    succeeded: texto extraído gravado como artefato derivado (nunca no original).
    failed: extração falhou — o original permanece intacto e o erro é rastreável.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExtractionReviewVerdict(str, enum.Enum):
    """Veredito da revisão humana sobre um texto extraído (Fase 3.5).

    confirmed: o advogado conferiu o derivado contra o original.
    extraction_error: o derivado contém erro de OCR/extração — a correção é um
    registro auditado, nunca uma substituição silenciosa do texto.
    """

    CONFIRMED = "confirmed"
    EXTRACTION_ERROR = "extraction_error"
