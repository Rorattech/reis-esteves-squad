"""Schemas Pydantic dos endpoints de execução e revisão humana do Intake (Fase 2.4).

tenant_id, case_id e actor_id nunca aparecem nestes schemas: tenant_id vem
do JWT, case_id vem da rota, actor_id vem do usuário autenticado
(CLAUDE.md, seção 7).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AuditActor, CaseArea, CaseStatus, FraudType, ModuleName, UrgencyLevel


class IntakeOutcomeSchema(str, enum.Enum):
    """Espelha `orchestrator.state.IntakeOutcome` (Fase 2.3) no lado da API."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    AWAITING_INFORMATION = "awaiting_information"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"


class IntakeResultResponse(BaseModel):
    """Resultado mais recente da execução do módulo Intake (coordinator + triage).

    Nunca uma decisão final (CLAUDE.md, seção 2) — `human_review_required`
    indica se ainda depende de aprovação humana antes de avançar.
    """

    case_id: uuid.UUID
    intake_outcome: IntakeOutcomeSchema | None
    platform: str
    fraud_type: FraudType
    urgency: UrgencyLevel
    area: CaseArea | None
    matter: str | None
    documents_requested: list[str]
    missing_information: list[str]
    out_of_scope_reason: str | None
    human_review_required: bool
    status: CaseStatus
    current_module: ModuleName


class IntakeReviewDecision(str, enum.Enum):
    """Ações de revisão humana disponíveis (docs/roadmap_mvp_squad_digital.md, 2.6)."""

    APPROVE = "approve"
    CORRECT = "correct"
    RETURN_FOR_INFORMATION = "return_for_information"


class IntakeReviewRequest(BaseModel):
    """Decisão do advogado sobre a recomendação de coordinator/triage.

    `notes` (justificativa) é obrigatório sempre que a decisão não for uma
    aprovação simples — mesma regra do roadmap ("campo obrigatório de
    justificativa quando houver correção ou devolução").
    """

    decision: IntakeReviewDecision
    notes: str | None = Field(default=None, max_length=4000)
    platform: str | None = Field(default=None, min_length=1, max_length=100)
    fraud_type: FraudType | None = None
    urgency: UrgencyLevel | None = None
    area: CaseArea | None = None
    matter: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _notes_required_unless_plain_approval(self) -> "IntakeReviewRequest":
        if self.decision != IntakeReviewDecision.APPROVE and not (
            self.notes and self.notes.strip()
        ):
            raise ValueError(
                "notes (justificativa) é obrigatório para 'correct' e 'return_for_information'."
            )
        return self


class CaseStageAdvanceRequest(BaseModel):
    """Decisão humana de concluir a abertura do caso e avançar para Evidências.

    Diferente de `IntakeReviewRequest`, não revisa nenhuma recomendação de IA
    — é usada quando não há recomendação a revisar (ver
    `app.services.intake_orchestration_service.advance_case_to_evidence`).
    `notes` é opcional: o avanço em si já fica registrado em audit_logs.
    """

    notes: str | None = Field(default=None, max_length=4000)


class AuditLogEntryResponse(BaseModel):
    """Representação pública de uma entrada de audit_logs, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    actor: AuditActor
    actor_id: str
    action: str
    module: ModuleName
    model_used: str
    tokens_used: int
    duration_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
