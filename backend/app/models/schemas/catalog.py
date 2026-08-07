"""Schemas Pydantic dos catálogos de classificação (plataformas e modalidades).

tenant_id nunca aparece nos schemas de escrita: é extraído do JWT pelo
TenantMiddleware (CLAUDE.md, seção 7). `slug` também não: é derivado do label
pelo serviço, para que o advogado não precise inventar identificadores.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import FraudType


class PlatformCreate(BaseModel):
    """Cadastro de uma plataforma pelo escritório (opção "Outro" do formulário)."""

    label: str = Field(min_length=1, max_length=100)


class FraudModalityCreate(BaseModel):
    """Cadastro de uma modalidade de golpe pelo escritório.

    `family` é obrigatório: uma modalidade sem família seria texto livre que o
    grafo e os prompts não sabem interpretar (ver app/models/catalog.py).
    """

    label: str = Field(min_length=1, max_length=100)
    family: FraudType


class PlatformResponse(BaseModel):
    """Representação pública de uma plataforma do catálogo."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    label: str
    is_system: bool
    active: bool
    sort_order: int
    created_at: datetime


class FraudModalityResponse(BaseModel):
    """Representação pública de uma modalidade do catálogo."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    label: str
    family: FraudType
    is_system: bool
    active: bool
    sort_order: int
    created_at: datetime
