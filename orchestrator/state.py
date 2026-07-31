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

IntakeOutcome = Literal[
    "completed", "blocked", "awaiting_information", "awaiting_human_review"
]
"""Estado explícito da etapa de Intake (módulo 1 — coordinator/triage):

- "completed": um nó concluiu sua própria classificação com confiança
  suficiente (estado interno de transição — o coordinator usa isso só para
  decidir se a triagem deve rodar em seguida, nunca é um estado final do caso).
- "blocked": caso fora do escopo do Squad Digital — precisa ser encaminhado
  manualmente (CLAUDE.md, seção 2: nenhum outro fluxo é inventado).
- "awaiting_information": dados insuficientes para classificar com confiança
  — o nó não inventa fatos ausentes, sinaliza o que falta.
- "awaiting_human_review": classificação/triagem concluída, mas — como todo
  output de agente (CLAUDE.md, seção 2) — é só uma recomendação até um
  advogado revisar e aprovar.
"""

AreaOfLaw = Literal["civil", "family", "criminal", "labor", "consumer", "digital"]
"""Área do Direito identificada na triagem (espelha CaseArea em
app/models/enums.py — prompts/digital/intake/triage.md)."""

EvidenceOutcome = Literal["awaiting_human_review", "awaiting_information"]
"""Estado explícito da etapa de Evidências (módulo 2 — documental/specialist):

- "awaiting_human_review": inventário e leitura técnica concluídos — como
  todo output de agente (CLAUDE.md, seção 2), é recomendação até um advogado
  revisar; o caso só avança para research após essa revisão explícita.
- "awaiting_information": evidências insuficientes para análise — os nós não
  inventam conteúdo ausente, sinalizam o que falta.
"""

FindingCategory = Literal["fact", "inference", "missing_info"]
"""Natureza de um achado probatório (roadmap 3.3 — o sistema distingue
claramente fato extraído, inferência técnica e ausência de informação)."""


class EvidenceRecord(BaseModel):
    """Entrada bruta de uma evidência para os nós do módulo Evidence.

    Montada pela camada de orquestração a partir de `evidence_files` +
    `evidence_extractions` (Fases 3.1/3.2) — os nós só leem daqui; nunca
    acessam banco ou storage diretamente.
    """

    evidence_id: str
    filename: str
    mime_type: str
    processing_status: str
    extracted_text: str | None = None
    extraction_confidence: float | None = None
    extraction_limitations: str | None = None


class EvidenceFinding(BaseModel):
    """Um achado probatório dos nós documental/specialist (roadmap 3.3).

    Todo achado com category "fact" ou "inference" DEVE apontar
    `source_evidence_id` para uma evidência original existente — achados sem
    origem rastreável são rejeitados pelo nó, nunca aceitos (roadmap 3.3:
    "Cada item deve ser rastreável até uma evidência original"). Lacunas
    (category "missing_info") são a única exceção: apontam o que NÃO existe.
    """

    finding_id: str
    source_evidence_id: str | None = None
    agent: Literal["documental", "specialist"]
    category: FindingCategory
    evidence_type: Literal[
        "screenshot", "payment_receipt", "fake_profile", "conversation", "url", "document", "other"
    ]
    summary: str
    relevance: Literal["low", "medium", "high"]
    suggested_use: str
    gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = True
    status: DraftStatus = "DRAFT_PENDING_REVIEW"


class SpecialistAssessment(BaseModel):
    """Leitura técnica da plataforma pelo Especialista Digital (roadmap 3.3).

    Contextualiza as evidências no funcionamento real da plataforma e da
    modalidade do golpe — hipóteses e recomendações de preservação, nunca
    conclusão jurídica definitiva (CLAUDE.md, seção 2).
    """

    platform_context: str
    platform_failure: str | None = None
    report_mechanism_analysis: str | None = None
    preservation_recommendations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    status: DraftStatus = "DRAFT_PENDING_REVIEW"


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
    narrative: str
    """Relato inicial em texto livre do cliente/advogado (equivalente a
    CaseIntake.narrative, backend/app/models/case_intake.py) — entrada
    principal dos nós coordinator/triage. Nunca inventado pelos agentes."""
    platform: str
    fraud_type: str
    urgency: Literal["low", "medium", "high", "critical"]
    area: AreaOfLaw | None
    """Área do Direito — preenchida pela triagem (None até lá)."""
    matter: str | None
    """Matéria específica dentro da área — preenchida pela triagem."""
    intake_outcome: IntakeOutcome | None
    """Resultado mais recente do módulo Intake — ver `IntakeOutcome`."""
    missing_information: list[str]
    """Lacunas de informação identificadas por coordinator/triage — nunca
    preenchidas com fatos inventados (CLAUDE.md, seção 2)."""
    out_of_scope_reason: str | None
    """Motivo pelo qual o coordinator marcou o caso como fora do escopo do
    Squad Digital — só preenchido quando intake_outcome == "blocked"."""
    documents_requested: list[str]
    evidence_records: list[EvidenceRecord]
    """Evidências brutas (arquivos + textos extraídos das Fases 3.1/3.2)
    carregadas pela orquestração antes de invocar o módulo Evidence — os nós
    nunca acessam banco/storage diretamente."""
    evidence_inventory: list[EvidenceItem]
    evidence_findings: list[EvidenceFinding]
    """Achados probatórios dos nós documental/specialist — cada um rastreável
    à evidência de origem (roadmap 3.3)."""
    specialist_assessment: SpecialistAssessment | None
    """Leitura técnica da plataforma pelo Especialista Digital (None até o
    módulo Evidence rodar)."""
    evidence_outcome: EvidenceOutcome | None
    """Resultado mais recente do módulo Evidence — ver `EvidenceOutcome`."""
    legal_sources: list[LegalSource]
    strategy_memo: StrategyMemo | None
    draft_petition: DraftPetition | None
    human_approval_required: bool
    human_approval_status: Literal["pending", "approved", "rejected", "na"]
    approved_by: str | None
    """Identificação do advogado que aprovou a etapa mais recente que exigia
    aprovação humana (CLAUDE.md, seção 9) — nível do caso como um todo, distinto
    de StrategyMemo.approved_by/DraftPetition.approved_by, que registram a
    aprovação de cada artefato individualmente.
    """
    approved_at: datetime | None
    """Timestamp da aprovação registrada em approved_by (CLAUDE.md, seção 9)."""
    audit_trail: list[AuditEntry]
    current_module: str
    status: Literal["active", "suspended", "completed", "error"]
