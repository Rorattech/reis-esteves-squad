"""Schemas Pydantic dos endpoints de caso (CaseCreate, CaseUpdate, CaseResponse).

tenant_id e user_id nunca aparecem em CaseCreate/CaseUpdate: são extraídos do
JWT pelo TenantMiddleware e nunca confiados a partir do payload do cliente
(CLAUDE.md, seção 7 — regra crítica de multitenancy).
"""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CaseArea, CaseStatus, FraudType, ModuleName, UrgencyLevel
from app.models.schemas.catalog import FraudModalityResponse, PlatformResponse
from app.models.schemas.client import ClientCreate, ClientSummary


class CaseCreate(BaseModel):
    """Dados para abertura de um novo caso pelo advogado autenticado.

    Classificação vem do catálogo do escritório (platform_id/fraud_modality_id,
    ver app/models/catalog.py), não de texto livre nem de enum fechado.

    O cliente pode chegar de duas formas, mutuamente exclusivas: `client_id`
    para um cliente já cadastrado, ou `client` com a qualificação de um cliente
    novo — que é criado na MESMA transação do caso, para que um caso que falha
    não deixe cliente órfão. Ambos podem faltar: o caso pode ser aberto antes
    de o cliente estar identificado, e vinculado depois.

    area/matter também são opcionais: podem ser preenchidos pela triagem
    (módulo intake) — ver prompts/digital/intake/triage.md.
    """

    platform_id: uuid.UUID
    fraud_modality_id: uuid.UUID
    urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    client_id: uuid.UUID | None = None
    client: ClientCreate | None = None
    area: CaseArea | None = None
    matter: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _reject_ambiguous_client(self) -> Self:
        """Impede informar cliente existente e cliente novo ao mesmo tempo.

        Sem isso a rota teria de escolher um dos dois silenciosamente, e o
        advogado descobriria a escolha errada só ao abrir o caso.
        """
        if self.client_id is not None and self.client is not None:
            raise ValueError(
                "Informe um cliente existente (client_id) ou os dados de um novo "
                "cliente (client) — nunca os dois."
            )
        return self


class CaseUpdate(BaseModel):
    """Campos atualizáveis de um caso existente — todos opcionais (semântica PATCH).

    `code` não aparece aqui: o identificador do caso é emitido uma vez e não é
    editável — é o que permite citá-lo com segurança fora do sistema.
    """

    platform_id: uuid.UUID | None = None
    fraud_modality_id: uuid.UUID | None = None
    urgency: UrgencyLevel | None = None
    status: CaseStatus | None = None
    client_id: uuid.UUID | None = None
    area: CaseArea | None = None
    matter: str | None = Field(default=None, max_length=255)
    current_module: ModuleName | None = None
    human_review_required: bool | None = None


class CaseSearchRequest(BaseModel):
    """Filtros de busca de casos, enviados no corpo — nunca na URL.

    Mesmo motivo de ClientSearchRequest: o termo casa com o nome do cliente,
    que é dado pessoal e não pode aparecer em access log nem em histórico de
    navegador (CLAUDE.md, seção 12).
    """

    search: str | None = Field(default=None, max_length=120)
    status: CaseStatus | None = None


class CaseResponse(BaseModel):
    """Representação pública de um caso, retornada pela API.

    `platform` e `fraud_type` continuam expostos como rótulo e família
    denormalizados (ver app/models/case.py) — quem só precisa exibir o caso não
    tem de resolver as entradas de catálogo. `client` traz nome e código, nunca
    o documento: CPF completo só em GET /api/v1/clients/{id}.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    code: str
    client_id: uuid.UUID | None
    client: ClientSummary | None
    area: CaseArea | None
    matter: str | None
    platform: str
    platform_entry: PlatformResponse
    fraud_type: FraudType
    fraud_modality: FraudModalityResponse
    urgency: UrgencyLevel
    status: CaseStatus
    current_module: ModuleName
    human_review_required: bool
    created_at: datetime
    updated_at: datetime
