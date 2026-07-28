"""CaseState — fonte única de verdade do caso, compartilhada por todos os nós
dos 6 módulos LangGraph (ver CLAUDE.md, seção 9, e docs/architecture.md,
seções 3.3 e 5, e glossário).

Ao criar um novo nó do grafo, retorne sempre um dict parcial com apenas os
campos que o nó efetivamente modificou — nunca o CaseState inteiro, e nunca
duplique estes campos em variáveis locais soltas (CLAUDE.md, seção 9).

case_id e tenant_id trafegam como str (não UUID) neste módulo porque o
CaseState é serializado pelo checkpointer do LangGraph a cada transição de nó
(docs/architecture.md, seção 3.3) — a conversão para UUID acontece na borda,
em backend/app, onde o tipo forte é reforçado pelo ORM e pelos schemas Pydantic.
"""

from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

ModuleName = Literal["intake", "evidence", "research", "strategy", "drafting", "review"]
"""Identificador dos 6 módulos do workflow jurídico (CLAUDE.md, seção 14)."""

ActorType = Literal["system", "agent", "human"]
"""Quem executou uma ação registrada em AuditEntry (CLAUDE.md, seção 10)."""

DraftStatus = Literal["DRAFT_PENDING_REVIEW", "APPROVED", "REJECTED"]
"""Status obrigatório de todo output jurídico gerado por IA (CLAUDE.md, seção 2)."""


class EvidenceItem(BaseModel):
    """Um item de evidência digital classificado no módulo Evidence Matrix
    (docs/architecture.md, seção 5, Módulo 2).
    """

    evidence_id: str
    evidence_type: Literal[
        "screenshot", "payment_receipt", "fake_profile", "conversation", "other"
    ]
    file_reference: str
    description: str
    relevance: Literal["low", "medium", "high"]
    legal_use: str
    extracted_text: str | None = None
    uploaded_at: datetime
    analyzed_at: datetime | None = None


class LegalSource(BaseModel):
    """Fonte jurídica verificável — legislação, jurisprudência ou doutrina.

    Schema obrigatório para todo output de pesquisa jurídica (CLAUDE.md, seção 8).
    O modelo nunca pode inventar precedentes, valores ou citações: se não houver
    fonte verificável, hallucination_risk deve ser True e excerpt não pode ser
    preenchido com texto inventado.
    """

    source_type: Literal["legislation", "jurisprudence", "doctrine"]
    title: str
    reference: str
    retrieved_at: datetime
    url: str | None = None
    excerpt: str
    confidence: float = Field(ge=0.0, le=1.0)
    verified: bool = False
    hallucination_risk: bool = False


class StrategyMemo(BaseModel):
    """Memorando de estratégia jurídica do Estrategista Sênior (módulo 4).

    Define competência, tutela de urgência, danos e viabilidade de ação
    coletiva — decisões jurídicas que exigem aprovação humana explícita antes
    de embasar a petição (CLAUDE.md, seção 2).
    """

    competencia: Literal["jec", "juizo_comum"]
    competencia_justificativa: str
    tutela_urgencia_recomendada: bool
    tutela_urgencia_justificativa: str
    material_damages_value: float = Field(ge=0.0)
    moral_damages_min: float = Field(ge=0.0)
    moral_damages_max: float = Field(ge=0.0)
    collective_action_possible: bool
    collective_action_justificativa: str
    legal_sources_used: list[str] = Field(default_factory=list)
    generated_at: datetime
    status: DraftStatus = "DRAFT_PENDING_REVIEW"
    approved_by: str | None = None
    approved_at: datetime | None = None
    content_hash: str | None = None


class DamagesTableEntry(BaseModel):
    """Uma linha da tabela de danos (material, moral ou total) da petição."""

    label: str
    value: float = Field(ge=0.0)


class DraftPetition(BaseModel):
    """Petição inicial em rascunho gerada pelo Drafting Engine (módulo 5).

    Nunca é a versão final protocolável — todo output jurídico é
    DRAFT_PENDING_REVIEW até aprovação humana explícita, registrada com
    actor_id, timestamp e hash do conteúdo aprovado (CLAUDE.md, seção 2).
    """

    petition_id: str
    structure: list[str]
    content_markdown: str
    damages_table: list[DamagesTableEntry] = Field(default_factory=list)
    version: int = 1
    generated_at: datetime
    status: DraftStatus = "DRAFT_PENDING_REVIEW"
    approved_by: str | None = None
    approved_at: datetime | None = None
    content_hash: str | None = None


class AuditEntry(BaseModel):
    """Entrada de auditoria de uma ação executada por um nó do grafo.

    Todo nó deve registrar uma entrada aqui antes de retornar (CLAUDE.md,
    seção 10) — audit_trail é um registro imutável, apenas append.
    """

    timestamp: datetime
    actor: ActorType
    actor_id: str
    action: str
    module: ModuleName
    input_hash: str
    output_hash: str
    model_used: str
    tokens_used: int
    duration_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseState(TypedDict):
    """Estado central do caso, trafegado entre todos os nós dos módulos LangGraph.

    É a única fonte de verdade do caso (CLAUDE.md, seção 9) — nenhum dado deve
    trafegar solto entre agentes fora deste objeto.
    """

    case_id: str
    tenant_id: str
    platform: str
    fraud_type: str
    urgency: Literal["low", "medium", "high", "critical"]
    documents_requested: list[str]
    evidence_inventory: list[EvidenceItem]
    legal_sources: list[LegalSource]
    strategy_memo: StrategyMemo | None
    draft_petition: DraftPetition | None
    human_approval_required: bool
    human_approval_status: Literal["pending", "approved", "rejected", "na"]
    audit_trail: list[AuditEntry]
    current_module: str
    status: Literal["active", "suspended", "completed", "error"]
