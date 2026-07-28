"""Schemas Pydantic dos endpoints de caso (CaseCreate, CaseUpdate, CaseResponse).

tenant_id e user_id nunca aparecem em CaseCreate/CaseUpdate: são extraídos do
JWT pelo TenantMiddleware e nunca confiados a partir do payload do cliente
(CLAUDE.md, seção 7 — regra crítica de multitenancy).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CaseStatus, FraudType, UrgencyLevel


class CaseCreate(BaseModel):
    """Dados para abertura de um novo caso pelo advogado autenticado."""

    platform: str = Field(min_length=1, max_length=100)
    fraud_type: FraudType
    urgency: UrgencyLevel = UrgencyLevel.MEDIUM


class CaseUpdate(BaseModel):
    """Campos atualizáveis de um caso existente — todos opcionais (semântica PATCH)."""

    platform: str | None = Field(default=None, min_length=1, max_length=100)
    fraud_type: FraudType | None = None
    urgency: UrgencyLevel | None = None
    status: CaseStatus | None = None


class CaseResponse(BaseModel):
    """Representação pública de um caso, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    platform: str
    fraud_type: FraudType
    urgency: UrgencyLevel
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
