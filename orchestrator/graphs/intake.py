"""Módulo 1 — Intake & Routing (docs/architecture.md, seção 5).

Por ora, só o nó de bootstrap existe: valida o CaseState recebido e prepara
o terreno para o Coordenador Digital (prompts/digital/intake/coordinator.md).
A classificação real (plataforma, modalidade, urgência) exige uma chamada a
um modelo de IA — ainda não implementada nesta fase (CLAUDE.md, seção 15,
"Não faça chamadas diretas ao modelo de IA fora dos nós do grafo LangGraph";
esse nó ainda não existe porque o cliente do modelo ainda não foi configurado).
"""

import time
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.audit import create_audit_entry
from orchestrator.state import CaseState

_REQUIRED_FIELDS = ("case_id", "tenant_id", "platform", "fraud_type")


class IntakeValidationError(Exception):
    """Levantada quando o CaseState recebido não tem os campos mínimos para iniciar o Intake."""


def bootstrap_case(state: CaseState) -> dict[str, Any]:
    """Valida o CaseState inicial e prepara o caso para o Coordenador Digital.

    Não classifica o caso — isso é responsabilidade do agente Coordenador,
    ainda não implementado nesta fase. Este nó só garante que os campos
    mínimos existem antes de qualquer agente atuar, e registra a auditoria
    da transição (CLAUDE.md, seção 10 — todo nó deve auditar antes de retornar).

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


def build_intake_graph() -> CompiledStateGraph:
    """Monta e compila o StateGraph do módulo Intake.

    Returns:
        Grafo compilado, pronto para `.invoke(state)`. Hoje só contém o nó
        `bootstrap_case` — o nó do Coordenador Digital (chamada de IA) será
        adicionado quando o módulo for implementado.
    """
    graph = StateGraph(CaseState)
    graph.add_node("bootstrap_case", bootstrap_case)
    graph.add_edge(START, "bootstrap_case")
    graph.add_edge("bootstrap_case", END)
    return graph.compile()
