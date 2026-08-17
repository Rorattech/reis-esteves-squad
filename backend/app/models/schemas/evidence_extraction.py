"""Schemas Pydantic dos artefatos de extração (Fase 3.2) e da revisão humana
do texto extraído (Fase 3.5).

O texto extraído sempre viaja acompanhado de confidence e limitations — a
interface é obrigada a apresentá-lo como conteúdo derivado, nunca como prova
perfeita (roadmap 3.2/3.5).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ExtractionOutcome, ExtractionReviewVerdict


class ExtractionReviewCreate(BaseModel):
    """Payload da revisão humana de um texto extraído."""

    verdict: ExtractionReviewVerdict
    note: str | None = Field(default=None, max_length=4000)


class ExtractionReviewResponse(BaseModel):
    """Revisão humana registrada — um veredito auditado, nunca uma substituição."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    extraction_id: uuid.UUID
    reviewer_id: uuid.UUID
    verdict: ExtractionReviewVerdict
    note: str | None
    created_at: datetime


class EvidenceExtractionResponse(BaseModel):
    """Uma execução do pipeline de extração, com o texto derivado e seus limites."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    evidence_id: uuid.UUID
    kind: str
    outcome: ExtractionOutcome
    extracted_text: str | None
    confidence: float | None
    # Leitura automática insuficiente: a interface é obrigada a destacar o
    # aviso e a conferência humana contra o original (roadmap 3.5).
    low_confidence: bool
    limitations: str | None
    tool_name: str
    tool_version: str
    input_sha256: str
    output_sha256: str | None
    duration_ms: int
    error_message: str | None
    created_at: datetime
    reviews: list[ExtractionReviewResponse] = []
