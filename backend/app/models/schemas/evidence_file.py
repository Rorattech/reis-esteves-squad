"""Schemas Pydantic dos arquivos de evidência de um caso (Fase 3.1).

storage_key nunca aparece em EvidenceFileResponse: é um detalhe interno de
armazenamento (app/core/storage.py) — o acesso ao conteúdo original só
acontece pela rota autenticada de download (GET .../evidence/{id}/download),
nunca por um caminho ou URL devolvido ao cliente.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field

from app.models.enums import EvidenceProcessingStatus


class EvidenceFileResponse(BaseModel):
    """Representação pública de um arquivo de evidência, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    case_id: uuid.UUID
    uploaded_by: uuid.UUID
    original_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    sha256_hash: str
    origin: str
    status: EvidenceProcessingStatus
    duplicate_of_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_duplicate(self) -> bool:
        """True se este upload tem o mesmo hash de uma evidência já existente no tenant."""
        return self.duplicate_of_id is not None
