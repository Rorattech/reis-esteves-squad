"""Stub de LLMClient (orchestrator/llm.py) para testes do módulo Intake.

Nenhum teste do projeto chama um provedor de IA real (CLAUDE.md, seção 15) —
este stub devolve respostas pré-definidas, na ordem em que os nós chamam
`complete()`, sem qualquer rede.
"""

from dataclasses import dataclass, field
from typing import Any

from orchestrator.llm import StructuredLLMResult


@dataclass
class StubLLMClient:
    """Devolve a próxima resposta de `responses` a cada chamada de `complete()`.

    Um cenário feliz de Intake completo (coordinator + triage) consome duas
    respostas, na ordem: `responses[0]` para o coordinator, `responses[1]`
    para a triagem. Cenários que terminam no coordinator (fora do escopo,
    informação insuficiente) só consomem `responses[0]`.
    """

    responses: list[dict[str, Any]]
    model_used: str = "stub-model"
    tokens_used: int = 42
    duration_ms: int = 7
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self, *, model: str, system_prompt: str, user_input: dict[str, Any]
    ) -> StructuredLLMResult:
        call_index = len(self.calls)
        self.calls.append(
            {"model": model, "system_prompt": system_prompt, "user_input": user_input}
        )
        return StructuredLLMResult(
            raw_output=self.responses[call_index],
            model_used=self.model_used,
            tokens_used=self.tokens_used,
            duration_ms=self.duration_ms,
        )
