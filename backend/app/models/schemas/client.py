"""Schemas Pydantic do cliente (ClientCreate, ClientUpdate, ClientResponse).

tenant_id nunca aparece em ClientCreate/ClientUpdate: é extraído do JWT pelo
TenantMiddleware, igual ao padrão de schemas/case.py (CLAUDE.md, seção 7).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ClientCreate(BaseModel):
    """Dados para o cadastro de um cliente (parte lesada) pelo tenant autenticado."""

    full_name: str = Field(min_length=1, max_length=255)
    document_number: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)


class ClientUpdate(BaseModel):
    """Campos atualizáveis de um cliente existente — todos opcionais (semântica PATCH)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    document_number: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)


class ClientResponse(BaseModel):
    """Representação pública de um cliente, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    full_name: str
    document_number: str | None
    email: str | None
    phone: str | None
    created_at: datetime
    updated_at: datetime
