"""Módulo 1 — Intake & Routing (docs/architecture.md, seção 5; CLAUDE.md, seção 14).

Três nós, nesta ordem: `bootstrap_case` (valida o CaseState recebido) →
`coordinator` (identifica se o caso é do Squad Digital, classifica
plataforma/modalidade/urgência preliminar) → `triage` (normaliza os dados,
produz o checklist de documentos faltantes e recomenda o próximo módulo).

Nenhuma saída destes nós é uma decisão final (CLAUDE.md, seção 2): tanto
`coordinator` quanto `triage` sempre terminam marcando o caso como
`human_approval_required=True`/`human_approval_status="pending"` exceto no
caminho interno "completed" do coordinator, que só existe para decidir se a
triagem deve rodar em seguida (ver `IntakeOutcome`, orchestrator/state.py).

O modelo de IA é acessado exclusivamente através de `orchestrator.llm.LLMClient`,
injetado via `Runtime[IntakeContext]` — nunca chamado diretamente aqui nem
em nenhum outro lugar fora de um nó do grafo (CLAUDE.md, seção 15).
"""

import time
import uuid
from dataclasses import dataclass
from typing import Any, TypeVar

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import create_audit_entry
from app.core.config import settings
from app.core.prompts import build_prompt_audit_metadata, load_prompt_bundle
from app.models.case import Case
from app.models.enums import CaseArea, CaseStatus, FraudType, UrgencyLevel
from orchestrator.llm import LLMClient, LLMNotConfiguredError, StructuredLLMResult
from orchestrator.state import CaseState, IntakeOutcome

_REQUIRED_FIELDS = ("case_id", "tenant_id", "platform", "fraud_type")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class IntakeValidationError(Exception):
    """Levantada quando o CaseState recebido não tem os campos mínimos para iniciar o Intake."""


class LLMOutputValidationError(Exception):
    """Levantada quando a saída bruta do modelo não valida contra o schema
    estruturado esperado (CoordinatorRecommendation/TriageRecommendation) —
    nunca é engolida ou substituída por um valor padrão inventado."""


@dataclass
class IntakeContext:
    """Dependências injetadas nos nós do módulo Intake via `Runtime[IntakeContext]`.

    Único ponto de acesso ao provedor de IA — nenhum nó importa um SDK de
    modelo diretamente (CLAUDE.md, seção 15).
    """

    llm_client: LLMClient


class CoordinatorRecommendation(BaseModel):
    """Saída estruturada do nó `coordinator` (prompts/digital/intake/coordinator.md).

    Espelha os campos do "Output Esperado" do prompt (PLATAFORMA RÉ,
    MODALIDADE, URGÊNCIA) em forma tipada e validável — nunca uma decisão
    final (CLAUDE.md, seção 2).
    """

    in_digital_scope: bool
    platform: str | None = None
    fraud_type: FraudType | None = None
    urgency: UrgencyLevel | None = None
    requires_more_information: bool = False
    missing_information: list[str] = Field(default_factory=list)
    out_of_scope_reason: str | None = None
    rationale: str


class TriageRecommendation(BaseModel):
    """Saída estruturada do nó `triage` (prompts/digital/intake/triage.md).

    Espelha os campos do "Output Esperado" do prompt (ÁREA, MATÉRIA,
    SÍNTESE, DOCUMENTOS FALTANDO) em forma tipada e validável — nunca uma
    decisão final (CLAUDE.md, seção 2).
    """

    area: CaseArea
    matter: str
    urgency: UrgencyLevel
    case_summary: str
    received_documents: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    requires_more_information: bool = False
    missing_information: list[str] = Field(default_factory=list)
    rationale: str


def bootstrap_case(state: CaseState) -> dict[str, Any]:
    """Valida o CaseState inicial e prepara o caso para o Coordenador Digital.

    Não classifica o caso — isso é responsabilidade do nó `coordinator`. Este
    nó só garante que os campos mínimos existem antes de qualquer agente
    atuar, e registra a auditoria da transição (CLAUDE.md, seção 10 — todo nó
    deve auditar antes de retornar).

    Args:
        state: CaseState recebido pelo módulo Intake.

    Returns:
        Dicionário parcial com os campos que este nó efetivamente modificou
        (CLAUDE.md, seção 9 — nunca o CaseState inteiro).

    Raises:
        IntakeValidationError: Se algum campo obrigatório estiver ausente/vazio.
    """
    missing = [field for field in _REQUIRED_FIELDS if not state.get(field)]
    if missing:
        raise IntakeValidationError(
            f"CaseState incompleto para iniciar o Intake — campos ausentes: {missing}"
        )

    start = time.monotonic()
    audit_entry = create_audit_entry(
        actor_id="system",
        action="validou os campos obrigatórios do caso antes do Coordenador Digital atuar",
        module="intake",
        input_data={field: state[field] for field in _REQUIRED_FIELDS},
        output_data={"current_module": "intake", "status": "active"},
        model_used="n/a",
        tokens_used=0,
        duration_ms=int((time.monotonic() - start) * 1000),
        actor="system",
    )

    return {
        "current_module": "intake",
        "status": "active",
        "audit_trail": [*state["audit_trail"], audit_entry],
    }


def _require_llm_client(runtime: Runtime[IntakeContext]) -> LLMClient:
    if runtime.context is None:
        raise LLMNotConfiguredError(
            "Nenhum LLMClient configurado — invoque o grafo com "
            "context=IntakeContext(llm_client=...) (ver orchestrator/llm.py)."
        )
    return runtime.context.llm_client


async def _call_structured(
    *,
    runtime: Runtime[IntakeContext],
    schema: type[SchemaT],
    system_prompt: str,
    user_input: dict[str, Any],
) -> tuple[SchemaT, StructuredLLMResult]:
    """Chama o LLMClient injetado e valida a saída bruta contra `schema`.

    Args:
        runtime: Runtime do LangGraph com `IntakeContext` (fornece o LLMClient).
        schema: Schema Pydantic esperado da saída (CoordinatorRecommendation
            ou TriageRecommendation).
        system_prompt: Prompt final já composto (`load_prompt_bundle(...).text`).
        user_input: Fatos do caso relevantes para esta chamada.

    Returns:
        Tupla (saída validada e tipada, resultado bruto do LLMClient — para
        extrair `model_used`/`tokens_used`/`duration_ms` para a auditoria).

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado via Runtime.
        LLMOutputValidationError: Se a saída bruta não validar contra `schema`
            — nunca é descartada silenciosamente nem substituída por um
            valor padrão inventado.
    """
    llm_client = _require_llm_client(runtime)
    result = await llm_client.complete(
        model=settings.intake_llm_model,
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


async def coordinator(state: CaseState, runtime: Runtime[IntakeContext]) -> dict[str, Any]:
    """Identifica escopo digital e classifica plataforma/modalidade/urgência preliminar.

    Sempre uma recomendação (CLAUDE.md, seção 2): quando o resultado é
    `intake_outcome="completed"`, o grafo segue para `triage`; nos demais
    casos (`blocked`/`awaiting_information`), o caso fica marcado como
    aguardando ação humana e a triagem não roda.

    Args:
        state: CaseState corrente — usa `narrative` e a classificação
            preliminar informada na abertura do caso.
        runtime: Runtime do LangGraph com o LLMClient injetado (`IntakeContext`).

    Returns:
        Dicionário parcial com os campos efetivamente modificados (CLAUDE.md,
        seção 9): classificação (quando houver), `intake_outcome`,
        `missing_information`, `out_of_scope_reason` e a entrada de auditoria.

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado.
        LLMOutputValidationError: Se a saída do modelo não validar contra
            `CoordinatorRecommendation`.
    """
    bundle = load_prompt_bundle("digital", "intake", "coordinator")
    user_input = {
        "narrative": state["narrative"],
        "platform_informado": state["platform"],
        "modalidade_informada": state["fraud_type"],
        "urgencia_informada": state["urgency"],
    }
    parsed, result = await _call_structured(
        runtime=runtime,
        schema=CoordinatorRecommendation,
        system_prompt=bundle.text,
        user_input=user_input,
    )

    outcome: IntakeOutcome
    if not parsed.in_digital_scope:
        outcome = "blocked"
    elif parsed.requires_more_information:
        outcome = "awaiting_information"
    else:
        outcome = "completed"

    metadata = build_prompt_audit_metadata(bundle)
    metadata["outcome"] = outcome
    metadata["in_digital_scope"] = parsed.in_digital_scope

    audit_entry = create_audit_entry(
        actor_id="coordinator",
        action="classificou plataforma, modalidade e urgência preliminar",
        module="intake",
        input_data=user_input,
        output_data=parsed.model_dump(mode="json"),
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        duration_ms=result.duration_ms,
        actor="agent",
        metadata=metadata,
    )

    updates: dict[str, Any] = {
        "intake_outcome": outcome,
        "missing_information": parsed.missing_information,
        "out_of_scope_reason": parsed.out_of_scope_reason,
        "audit_trail": [*state["audit_trail"], audit_entry],
    }
    if parsed.platform:
        updates["platform"] = parsed.platform
    if parsed.fraud_type is not None:
        updates["fraud_type"] = parsed.fraud_type.value
    if parsed.urgency is not None:
        updates["urgency"] = parsed.urgency.value
    if outcome != "completed":
        # "completed" aqui é só um estado interno de transição para decidir
        # se a triagem roda em seguida — os dois desfechos finais deste nó
        # (blocked/awaiting_information) já exigem ação humana imediata.
        updates["human_approval_required"] = True
        updates["human_approval_status"] = "pending"

    return updates


async def triage(state: CaseState, runtime: Runtime[IntakeContext]) -> dict[str, Any]:
    """Normaliza área/matéria/urgência, monta o checklist de documentos e
    recomenda o próximo módulo — sempre como recomendação revisável.

    Só roda quando `coordinator` retornou `intake_outcome="completed"`
    (ver `_route_after_coordinator`).

    Args:
        state: CaseState corrente — usa `narrative` e a classificação
            preliminar produzida por `coordinator`.
        runtime: Runtime do LangGraph com o LLMClient injetado (`IntakeContext`).

    Returns:
        Dicionário parcial com os campos efetivamente modificados: `area`,
        `matter`, `urgency` (final), `documents_requested` (checklist de
        faltantes), `intake_outcome`, `missing_information`, os campos de
        aprovação humana e a entrada de auditoria.

    Raises:
        LLMNotConfiguredError: Se nenhum LLMClient foi injetado.
        LLMOutputValidationError: Se a saída do modelo não validar contra
            `TriageRecommendation`.
    """
    bundle = load_prompt_bundle("digital", "intake", "triage")
    user_input = {
        "narrative": state["narrative"],
        "platform": state["platform"],
        "modalidade": state["fraud_type"],
        "urgencia_preliminar": state["urgency"],
    }
    parsed, result = await _call_structured(
        runtime=runtime,
        schema=TriageRecommendation,
        system_prompt=bundle.text,
        user_input=user_input,
    )

    outcome: IntakeOutcome = (
        "awaiting_information" if parsed.requires_more_information else "awaiting_human_review"
    )

    metadata = build_prompt_audit_metadata(bundle)
    metadata["outcome"] = outcome
    metadata["recommended_next_module"] = "evidence" if outcome == "awaiting_human_review" else None

    audit_entry = create_audit_entry(
        actor_id="triage",
        action="normalizou os dados e produziu o checklist de documentos faltantes",
        module="intake",
        input_data=user_input,
        output_data=parsed.model_dump(mode="json"),
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        duration_ms=result.duration_ms,
        actor="agent",
        metadata=metadata,
    )

    return {
        "area": parsed.area.value,
        "matter": parsed.matter,
        "urgency": parsed.urgency.value,
        "documents_requested": parsed.missing_documents,
        "intake_outcome": outcome,
        "missing_information": parsed.missing_information,
        "human_approval_required": True,
        "human_approval_status": "pending",
        "audit_trail": [*state["audit_trail"], audit_entry],
    }


def _route_after_coordinator(state: CaseState) -> str:
    """Decide se a triagem roda em seguida — só quando o coordinator concluiu
    a classificação preliminar dentro do escopo do Squad Digital.
    """
    return "triage" if state["intake_outcome"] == "completed" else END


def build_intake_graph() -> CompiledStateGraph:
    """Monta e compila o StateGraph do módulo Intake.

    Requer um `IntakeContext` (com o `LLMClient` injetado) na invocação:

        await graph.ainvoke(state, context=IntakeContext(llm_client=meu_client))

    Returns:
        Grafo compilado: `bootstrap_case` → `coordinator` → (`triage` | fim),
        conforme `intake_outcome` (ver `IntakeOutcome`, orchestrator/state.py).
    """
    graph = StateGraph(CaseState, context_schema=IntakeContext)
    graph.add_node("bootstrap_case", bootstrap_case)
    graph.add_node("coordinator", coordinator)
    graph.add_node("triage", triage)
    graph.add_edge(START, "bootstrap_case")
    graph.add_edge("bootstrap_case", "coordinator")
    graph.add_conditional_edges(
        "coordinator", _route_after_coordinator, {"triage": "triage", END: END}
    )
    graph.add_edge("triage", END)
    return graph.compile()


async def persist_intake_recommendation(session: AsyncSession, state: CaseState) -> Case:
    """Grava no `Case` (SQLAlchemy) a recomendação mais recente do módulo Intake.

    Nunca marca o caso como aprovado — só registra platform/fraud_type/
    urgency/area/matter e sinaliza `human_review_required=True`; a aprovação
    humana em si é responsabilidade da API de revisão (Fase 2.4).

    Args:
        session: Sessão do banco já escopada por tenant (CLAUDE.md, seção 7).
        state: CaseState após `coordinator`/`triage` terem rodado.

    Returns:
        O `Case` atualizado.

    Raises:
        IntakeValidationError: Se o caso não existir para o tenant do state
            (nunca atualiza um caso sem confirmar o tenant_id — CLAUDE.md,
            seção 7).
    """
    tenant_id = uuid.UUID(state["tenant_id"])
    case_id = uuid.UUID(state["case_id"])

    case = await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))
    if case is None:
        raise IntakeValidationError(
            f"Caso {case_id} não encontrado para o tenant {tenant_id} — nada a persistir."
        )

    # platform/fraud_type NÃO são escritos aqui: desde a Fase 2.7 eles são
    # rótulo e família derivados da entrada de catálogo escolhida pelo advogado
    # (ver app/models/case.py), e a triagem não escolhe entrada de catálogo. A
    # leitura do agente continua no CaseState e é exibida como recomendação —
    # ela só vira classificação do caso quando um humano corrige explicitamente
    # (IntakeReviewDecision.CORRECT), que é o modelo exigido por CLAUDE.md §2.
    case.urgency = UrgencyLevel(state["urgency"])
    if state.get("area"):
        case.area = CaseArea(state["area"])
    if state.get("matter"):
        case.matter = state["matter"]
    case.human_review_required = True
    case.status = (
        CaseStatus.PENDING_APPROVAL
        if state.get("intake_outcome") == "awaiting_human_review"
        else CaseStatus.IN_PROGRESS
    )

    await session.flush()
    return case
