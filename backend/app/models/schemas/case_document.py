"""Schemas Pydantic do checklist de documentos de um caso.

tenant_id e case_id nunca aparecem em CaseDocumentCreate/Update: tenant_id
vem do JWT, case_id vem da rota (CLAUDE.md, seção 7).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import DocumentChecklistStatus


class CaseDocumentCreate(BaseModel):
    """Novo item do checklist de documentos de um caso."""

    name: str = Field(min_length=1, max_length=255)
    status: DocumentChecklistStatus = DocumentChecklistStatus.PENDING
    origin: str = Field(default="intake", max_length=50)
    notes: str | None = None


class CaseDocumentUpdate(BaseModel):
    """Campos atualizáveis de um item do checklist — todos opcionais (semântica PATCH)."""

    status: DocumentChecklistStatus | None = None
    notes: str | None = None


class CaseDocumentResponse(BaseModel):
    """Representação pública de um item do checklist, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    case_id: uuid.UUID
    name: str
    status: DocumentChecklistStatus
    origin: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
