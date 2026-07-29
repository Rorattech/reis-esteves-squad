"""Roteamento entre os 6 módulos do workflow jurídico (CLAUDE.md, seção 14;
docs/architecture.md, seção 3.3).

Decide qual módulo executar em seguida com base no CaseState — nunca a
lógica inversa (um módulo decidindo por si só qual é o próximo). Cada módulo
é um StateGraph independente (orchestrator/graphs/); este router só encadeia
as invocações entre eles.
"""

from orchestrator.state import CaseState, ModuleName

MODULE_ORDER: tuple[ModuleName, ...] = (
    "intake",
    "evidence",
    "research",
    "strategy",
    "drafting",
    "review",
)


def next_module(current: ModuleName) -> ModuleName | None:
    """Retorna o módulo seguinte na sequência fixa do workflow.

    Args:
        current: Módulo atualmente ativo.

    Returns:
        O próximo módulo na sequência, ou None se `current` for o último
        (review) ou não pertencer a MODULE_ORDER.
    """
    try:
        index = MODULE_ORDER.index(current)
    except ValueError:
        return None
    if index + 1 >= len(MODULE_ORDER):
        return None
    return MODULE_ORDER[index + 1]


def route(state: CaseState) -> ModuleName | None:
    """Decide o próximo módulo a executar para um CaseState.

    Um caso não avança enquanto estiver `suspended` aguardando aprovação
    humana (CLAUDE.md, seção 2 — human-in-the-loop) nem depois de
    `completed`/`error`.

    Args:
        state: Estado atual do caso.

    Returns:
        O próximo módulo a ser invocado, ou None se o caso não deve avançar
        agora (suspenso aguardando aprovação, concluído, ou em erro).
    """
    if state["status"] in ("suspended", "completed", "error"):
        return None
    if state["human_approval_required"] and state["human_approval_status"] == "pending":
        return None
    return next_module(state["current_module"])
