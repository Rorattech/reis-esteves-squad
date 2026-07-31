"""Schemas Pydantic da análise de evidências (Fase 3.3 — módulo evidence).

Todo achado nasce DRAFT_PENDING_REVIEW e só muda por revisão humana
explícita (CLAUDE.md, seção 2). A resposta de análise carrega sempre
`human_review_required` — a interface é obrigada a exibir a pendência.
"""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CaseStatus, ModuleName


class EvidenceReviewDecision(str, enum.Enum):
    """Ações de revisão humana sobre o inventário probatório (roadmap 3.3)."""

    APPROVE = "approve"
    RETURN_FOR_INFORMATION = "return_for_information"


class EvidenceReviewRequest(BaseModel):
    """Decisão do advogado sobre a análise de evidências.

    `notes` é obrigatório quando a decisão devolve o caso — mesma regra da
    revisão do Intake (justificativa em devoluções).
    """

    decision: EvidenceReviewDecision
    notes: str | None = Field(default=None, max_length=4000)


class EvidenceFindingResponse(BaseModel):
    """Um achado probatório persistido, rastreável à evidência de origem."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    evidence_id: uuid.UUID | None
    agent: str
    category: str
    evidence_type: str
    summary: str
    relevance: str
    suggested_use: str
    gaps: list[str]
    confidence: float
    status: str
    created_at: datetime


class SpecialistAssessmentResponse(BaseModel):
    """Leitura técnica do Especialista Digital — sempre pendente de revisão."""

    platform_context: str
    platform_failure: str | None
    report_mechanism_analysis: str | None
    preservation_recommendations: list[str]
    hypotheses: list[str]
    status: str


class EvidenceAnalysisResultResponse(BaseModel):
    """Resultado consolidado do módulo Evidence para a interface (Fase 3.4/3.5)."""

    case_id: uuid.UUID
    evidence_outcome: str | None
    findings: list[EvidenceFindingResponse]
    specialist_assessment: SpecialistAssessmentResponse | None
    documents_requested: list[str]
    human_review_required: bool
    status: CaseStatus
    current_module: ModuleName
