"""Schemas Pydantic do relato inicial de um caso (CaseIntakeCreate/Update/Response).

tenant_id, case_id e submitted_by nunca aparecem em CaseIntakeCreate/Update:
tenant_id vem do JWT, case_id vem da rota, submitted_by vem do usuário
autenticado (CLAUDE.md, seção 7).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class CaseIntakeCreate(BaseModel):
    """Relato inicial de um caso — texto livre + campos estruturados do primeiro contato."""

    narrative: str = Field(min_length=1)
    estimated_loss_amount: Decimal | None = Field(default=None, ge=0)
    incident_date: date | None = None
    has_police_report: bool | None = None
    claimed_documents: list[str] = Field(default_factory=list)
    pending_information: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseIntakeUpdate(BaseModel):
    """Campos atualizáveis do relato inicial — todos opcionais (semântica PATCH)."""

    narrative: str | None = Field(default=None, min_length=1)
    estimated_loss_amount: Decimal | None = Field(default=None, ge=0)
    incident_date: date | None = None
    has_police_report: bool | None = None
    claimed_documents: list[str] | None = None
    pending_information: list[str] | None = None
    metadata: dict[str, Any] | None = None


class CaseIntakeResponse(BaseModel):
    """Representação pública do relato inicial, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    case_id: uuid.UUID
    submitted_by: uuid.UUID
    narrative: str
    estimated_loss_amount: Decimal | None
    incident_date: date | None
    has_police_report: bool | None
    claimed_documents: list[str]
    pending_information: list[str]
    created_at: datetime
    updated_at: datetime
