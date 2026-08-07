"""Módulo 2 — Evidence (docs/architecture.md, seção 5; CLAUDE.md, seção 14).

Três nós, nesta ordem: `bootstrap_evidence` (valida o CaseState e as
evidências carregadas) → `documental` (inventário probatório rastreável:
documentos, prints, comprovantes, URLs e lacunas) → `specialist` (leitura
técnica da plataforma/modalidade, distinguindo fato extraído, inferência
técnica e informação pendente).

Regras inegociáveis (roadmap 3.3):
- Cada achado com category "fact"/"inference" DEVE apontar para uma evidência
  original existente (`source_evidence_id`) — achados sem origem rastreável
  são rejeitados com `EvidenceTraceabilityError`, nunca aceitos.
- Os nós não inventam conteúdo ausente: lacunas viram achados
  category="missing_info", não fatos.
- Nenhuma conclusão jurídica definitiva: todo output termina
  `human_approval_required=True` e `status: "DRAFT_PENDING_REVIEW"`.

O modelo de IA é acessado exclusivamente via `orchestrator.llm.LLMClient`,
injetado via `Runtime[EvidenceContext]` (CLAUDE.md, seção 15).
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, ValidationError

from app.core.audit import create_audit_entry
from app.core.config import settings
from app.core.prompts import build_prompt_audit_metadata, load_prompt_bundle
from orchestrator.llm import LLMClient, LLMNotConfiguredError, StructuredLLMResult
from orchestrator.state import (
    CaseState,
    EvidenceFinding,
    EvidenceItem,
    EvidenceRecord,
    FindingCategory,
    SpecialistAssessment,
)

_REQUIRED_FIELDS = ("case_id", "tenant_id", "platform", "fraud_type")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class EvidenceGraphValidationError(Exception):
    """Levantada quando o CaseState não tem o mínimo para o módulo Evidence rodar."""


class EvidenceTraceabilityError(Exception):
    """Levantada quando o modelo produz um achado sem vínculo rastreável com
    uma evidência original — nunca aceito silenciosamente (roadmap 3.3)."""


class LLMOutputValidationError(Exception):
    """Levantada quando a saída bruta do modelo não valida contra o schema
    estruturado esperado (DocumentalReport/SpecialistReport) — nunca engolida
    nem substituída por um valor padrão inventado."""


@dataclass
class EvidenceContext:
    """Dependências injetadas nos nós do módulo Evidence via `Runtime[EvidenceContext]`."""

    llm_client: LLMClient


class FindingModel(BaseModel):
    """Um achado na saída bruta do modelo (documental ou specialist).

    Espelha `orchestrator.state.EvidenceFinding` sem os campos que o nó
    preenche sozinho (finding_id, agent, requires_human_review, status).
    """

    source_evidence_id: str | None = None
    category: FindingCategory
    evidence_type: Literal[
        "screenshot",
        "payment_receipt",
        "fake_profile",
        "conversation",
        "url",
        "document",
        "other",
    ]
    summary: str
    relevance: Literal["low", "medium", "high"]
    suggested_use: str
    gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class DocumentalItemAnalysis(BaseModel):
    """Análise de uma evidência individual pelo nó documental."""

    evidence_id: str
    evidence_type: Literal[
        "screenshot",
        "payment_receipt",
        "fake_profile",
        "conversation",
        "url",
        "document",
        "other",
    ]
    description: str
    relevance: Literal["low", "medium", "high"]
    legal_use: str


class DocumentalReport(BaseModel):
    """Saída estruturada do nó `documental` (prompts/digital/evidence/documental.md)."""

    items: list[DocumentalItemAnalysis] = Field(default_factory=list)
    findings: list[FindingModel] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    rationale: str


class SpecialistReport(BaseModel):
    """Saída estruturada do nó `specialist` (prompts/digital/evidence/specialist.md)."""

    platform_context: str
    platform_failure: str | None = None
    report_mechanism_analysis: str | None = None
    preservation_recommendations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    findings: list[FindingModel] = Field(default_factory=list)
    rationale: str


def bootstrap_evidence(state: CaseState) -> dict[str, Any]:
    """Valida o CaseState e as evidências carregadas antes dos agentes atuarem.

    Não analisa nada — só garante que os campos mínimos e ao menos uma
    evidência existem, e registra a auditoria da transição (CLAUDE.md,
    seção 10).

    Args:
        state: CaseState recebido pelo módulo Evidence, com
            `evidence_records` já carregados pela orquestração.

    Returns:
        Dicionário parcial com os campos que este nó efetivamente modificou.

    Raises:
        EvidenceGraphValidationError: Se faltar campo obrigatório ou não
            houver nenhuma evidência anexada.
    """
    missing = [field for field in _REQUIRED_FIELDS if not state.get(field)]
    if missing:
        raise EvidenceGraphValidationError(
            f"CaseState incompleto para o módulo Evidence — campos ausentes: {missing}"
        )
    if not state["evidence_records"]:
        raise EvidenceGraphValidationError(
            "Nenhuma evidência anexada ao caso — o módulo Evidence não roda sem "
            "ao menos um arquivo (os agentes nunca inventam provas)."
        )

    start = time.monotonic()
    audit_entry = create_audit_entry(
        actor_id="system",
        action="validou o caso e as evidências carregadas antes da análise documental",
        module="evidence",
        input_data={
            "evidence_count": len(state["evidence_records"]),
            "with_extracted_text": sum(
                1 for record in state["evidence_records"] if record.extracted_text
            ),
        },
        output_data={"current_module": "evidence", "status": "active"},
        model_used="n/a",
        tokens_used=0,
        duration_ms=int((time.monotonic() - start) * 1000),
        actor="system",
    )
    return {
        "current_module": "evidence",
        "status": "active",
        "audit_trail": [*state["audit_trail"], audit_entry],
    }


def _require_llm_client(runtime: Runtime[EvidenceContext]) -> LLMClient:
    if runtime.context is None:
        raise LLMNotConfiguredError(
            "Nenhum LLMClient configurado — invoque o grafo com "
            "context=EvidenceContext(llm_client=...) (ver orchestrator/llm.py)."
        )
    return runtime.context.llm_client


async def _call_structured(
    *,
    runtime: Runtime[EvidenceContext],
    schema: type[SchemaT],
    system_prompt: str,
    user_input: dict[str, Any],
) -> tuple[SchemaT, StructuredLLMResult]:
    """Chama o LLMClient injetado e valida a saída bruta contra `schema`.

    Args:
        runtime: Runtime do LangGraph com `EvidenceContext`.
        schema: Schema Pydantic esperado (DocumentalReport/SpecialistReport).
        system_prompt: Prompt final já composto (`load_prompt_bundle(...).text`).
        user_input: Evidências e contexto do caso relevantes para a chamada.

    Returns:
        Tupla (saída validada e tipada, resultado bruto do LLMClient).

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado.
        LLMOutputValidationError: Se a saída bruta não validar contra `schema`.
    """
    llm_client = _require_llm_client(runtime)
    result = await llm_client.complete(
        model=settings.evidence_llm_model,
        system_prompt=system_prompt,
        user_input=user_input,
    )
    try:
        parsed = schema.model_validate(result.raw_output)
    except ValidationError as exc:
        raise LLMOutputValidationError(
            f"Saída do modelo não passou na validação de {schema.__name__}: {exc}"
        ) from exc
    return parsed, result


def _validate_traceability(
    findings: list[FindingModel], records: list[EvidenceRecord], *, agent: str
) -> None:
    """Rejeita achados "fact"/"inference" sem vínculo com uma evidência real.

    Raises:
        EvidenceTraceabilityError: Se algum achado apontar para uma evidência
            inexistente, ou não apontar para nenhuma sem ser lacuna.
    """
    known_ids = {record.evidence_id for record in records}
    for finding in findings:
        if finding.category == "missing_info":
            continue
        if finding.source_evidence_id is None:
            raise EvidenceTraceabilityError(
                f"Achado do agente {agent} sem evidência de origem "
                f"(category={finding.category!r}: {finding.summary[:80]!r}) — "
                "todo fato/inferência deve ser rastreável a uma evidência original."
            )
        if finding.source_evidence_id not in known_ids:
            raise EvidenceTraceabilityError(
                f"Achado do agente {agent} referencia evidência inexistente "
                f"{finding.source_evidence_id!r} — o modelo não pode inventar provas."
            )


def _to_findings(
    findings: list[FindingModel], *, agent: Literal["documental", "specialist"]
) -> list[EvidenceFinding]:
    return [
        EvidenceFinding(
            finding_id=str(uuid.uuid4()),
            source_evidence_id=finding.source_evidence_id,
            agent=agent,
            category=finding.category,
            evidence_type=finding.evidence_type,
            summary=finding.summary,
            relevance=finding.relevance,
            suggested_use=finding.suggested_use,
            gaps=finding.gaps,
            confidence=finding.confidence,
        )
        for finding in findings
    ]


def _records_payload(records: list[EvidenceRecord]) -> list[dict[str, Any]]:
    return [record.model_dump(mode="json") for record in records]


async def documental(state: CaseState, runtime: Runtime[EvidenceContext]) -> dict[str, Any]:
    """Cria o inventário probatório rastreável (documentos, prints, lacunas).

    Cada item analisado e cada achado apontam para a evidência de origem; o
    nó rejeita qualquer achado sem vínculo (roadmap 3.3: "não inventa
    conteúdo ausente"). Documentos faltantes viram achados
    category="missing_info" — nunca fatos.

    Args:
        state: CaseState corrente — usa `evidence_records` e a classificação
            do Intake.
        runtime: Runtime do LangGraph com o LLMClient injetado.

    Returns:
        Dicionário parcial: `evidence_inventory`, `evidence_findings`,
        `documents_requested` e a entrada de auditoria.

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado.
        LLMOutputValidationError: Se a saída do modelo não validar contra
            `DocumentalReport`.
        EvidenceTraceabilityError: Se algum achado não for rastreável.
    """
    bundle = load_prompt_bundle("digital", "evidence", "documental")
    user_input = {
        # case_code, e não o nome do cliente: o cabeçalho do relatório precisa
        # identificar o processo sem mandar dado pessoal para o modelo.
        "case_code": state["case_code"],
        "platform": state["platform"],
        "fraud_type": state["fraud_type"],
        "matter": state["matter"],
        "narrative": state["narrative"],
        "evidence_records": _records_payload(state["evidence_records"]),
    }
    parsed, result = await _call_structured(
        runtime=runtime,
        schema=DocumentalReport,
        system_prompt=bundle.text,
        user_input=user_input,
    )
    _validate_traceability(parsed.findings, state["evidence_records"], agent="documental")

    known_ids = {record.evidence_id for record in state["evidence_records"]}
    invalid_items = [item.evidence_id for item in parsed.items if item.evidence_id not in known_ids]
    if invalid_items:
        raise EvidenceTraceabilityError(
            f"Inventário referencia evidências inexistentes: {invalid_items} — "
            "o modelo não pode inventar provas."
        )

    # EvidenceItem aceita um subconjunto dos tipos de FindingModel — os
    # demais ("url", "document") entram como "other" no inventário.
    item_types = ("screenshot", "payment_receipt", "fake_profile", "conversation")
    records_by_id = {record.evidence_id: record for record in state["evidence_records"]}
    inventory = [
        EvidenceItem(
            evidence_id=item.evidence_id,
            evidence_type=(item.evidence_type if item.evidence_type in item_types else "other"),
            file_reference=records_by_id[item.evidence_id].filename,
            description=item.description,
            relevance=item.relevance,
            legal_use=item.legal_use,
            extracted_text=records_by_id[item.evidence_id].extracted_text,
            uploaded_at=_now(),
            analyzed_at=_now(),
        )
        for item in parsed.items
    ]
    findings = _to_findings(parsed.findings, agent="documental")

    metadata = build_prompt_audit_metadata(bundle)
    metadata["items_count"] = len(inventory)
    metadata["findings_count"] = len(findings)
    metadata["missing_documents_count"] = len(parsed.missing_documents)

    audit_entry = create_audit_entry(
        actor_id="documental",
        action="produziu o inventário probatório rastreável do caso",
        module="evidence",
        input_data={
            "evidence_count": len(state["evidence_records"]),
            "platform": state["platform"],
            "fraud_type": state["fraud_type"],
        },
        output_data=parsed.model_dump(mode="json"),
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        duration_ms=result.duration_ms,
        actor="agent",
        metadata=metadata,
    )

    return {
        "evidence_inventory": inventory,
        "evidence_findings": findings,
        "documents_requested": sorted({*state["documents_requested"], *parsed.missing_documents}),
        "audit_trail": [*state["audit_trail"], audit_entry],
    }


async def specialist(state: CaseState, runtime: Runtime[EvidenceContext]) -> dict[str, Any]:
    """Contextualiza tecnicamente as evidências na plataforma e modalidade.

    Distingue fato extraído, inferência técnica e informação pendente
    (category de cada achado), aponta hipóteses e recomendações de
    preservação — nunca conclusão jurídica definitiva (CLAUDE.md, seção 2).
    Ao final, o módulo fica aguardando revisão humana: o caso só avança para
    research após aprovação explícita (roadmap 3.3).

    Args:
        state: CaseState corrente — usa `evidence_records`, o inventário do
            nó documental e a classificação do Intake.
        runtime: Runtime do LangGraph com o LLMClient injetado.

    Returns:
        Dicionário parcial: `specialist_assessment`, `evidence_findings`
        (acumulado), `evidence_outcome`, campos de aprovação humana e a
        entrada de auditoria.

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado.
        LLMOutputValidationError: Se a saída do modelo não validar contra
            `SpecialistReport`.
        EvidenceTraceabilityError: Se algum achado não for rastreável.
    """
    bundle = load_prompt_bundle("digital", "evidence", "specialist")
    user_input = {
        "case_code": state["case_code"],
        "platform": state["platform"],
        "fraud_type": state["fraud_type"],
        "matter": state["matter"],
        # Comarca do cliente: base do foro do consumidor (CDC art. 101, I), que
        # o prompt precisa recomendar. Nome/CPF/endereço completo nunca vêm.
        "client_city": state["client_city"],
        "client_state": state["client_state"],
        "evidence_records": _records_payload(state["evidence_records"]),
        "documental_findings": [
            finding.model_dump(mode="json") for finding in state["evidence_findings"]
        ],
    }
    parsed, result = await _call_structured(
        runtime=runtime,
        schema=SpecialistReport,
        system_prompt=bundle.text,
        user_input=user_input,
    )
    _validate_traceability(parsed.findings, state["evidence_records"], agent="specialist")

    assessment = SpecialistAssessment(
        platform_context=parsed.platform_context,
        platform_failure=parsed.platform_failure,
        report_mechanism_analysis=parsed.report_mechanism_analysis,
        preservation_recommendations=parsed.preservation_recommendations,
        hypotheses=parsed.hypotheses,
    )
    findings = _to_findings(parsed.findings, agent="specialist")

    metadata = build_prompt_audit_metadata(bundle)
    metadata["findings_count"] = len(findings)
    metadata["outcome"] = "awaiting_human_review"

    audit_entry = create_audit_entry(
        actor_id="specialist",
        action="contextualizou tecnicamente as evidências na plataforma e modalidade",
        module="evidence",
        input_data={
            "platform": state["platform"],
            "fraud_type": state["fraud_type"],
            "documental_findings_count": len(state["evidence_findings"]),
        },
        output_data=parsed.model_dump(mode="json"),
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        duration_ms=result.duration_ms,
        actor="agent",
        metadata=metadata,
    )

    return {
        "specialist_assessment": assessment,
        "evidence_findings": [*state["evidence_findings"], *findings],
        "evidence_outcome": "awaiting_human_review",
        "human_approval_required": True,
        "human_approval_status": "pending",
        "audit_trail": [*state["audit_trail"], audit_entry],
    }


def _now() -> datetime:
    return datetime.now(UTC)


def build_evidence_graph() -> CompiledStateGraph:
    """Monta e compila o StateGraph do módulo Evidence.

    Requer um `EvidenceContext` (com o `LLMClient` injetado) na invocação:

        await graph.ainvoke(state, context=EvidenceContext(llm_client=meu_client))

    Returns:
        Grafo compilado: `bootstrap_evidence` → `documental` → `specialist`,
        terminando sempre em aguardo de revisão humana — o encaminhamento ao
        módulo research só acontece via revisão explícita
        (`app/services/evidence_orchestration_service.py::review_evidence_findings`).
    """
    graph = StateGraph(CaseState, context_schema=EvidenceContext)
    graph.add_node("bootstrap_evidence", bootstrap_evidence)
    graph.add_node("documental", documental)
    graph.add_node("specialist", specialist)
    graph.add_edge(START, "bootstrap_evidence")
    graph.add_edge("bootstrap_evidence", "documental")
    graph.add_edge("documental", "specialist")
    graph.add_edge("specialist", END)
    return graph.compile()
