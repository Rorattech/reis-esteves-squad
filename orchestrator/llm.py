"""Abstração do provedor de modelo de IA usada pelos nós do grafo.

Nenhum nó do grafo pode chamar a SDK de um provedor de IA diretamente
(CLAUDE.md, seção 15 — "Não faça chamadas diretas ao modelo de IA fora dos
nós do grafo LangGraph"). Este módulo define o contrato mínimo (`LLMClient`)
que qualquer provedor precisa implementar; a implementação concreta (ex.:
SDK da Anthropic) ainda não existe neste projeto — quando existir, deve
morar aqui ou em um módulo irmão, nunca inline dentro de um nó.

Enquanto isso, os nós recebem o client via `Runtime[IntakeContext]`
(mecanismo nativo do LangGraph — CLAUDE.md, seção 15: "use LangGraph, que já
inclui o necessário" — nunca via `langchain_core`), o que torna trivial
stubar/mockar o provedor em testes, sem qualquer chamada de rede real.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StructuredLLMResult:
    """Resultado bruto de uma chamada ao modelo — ainda não validado contra schema algum.

    A validação contra um schema Pydantic específico é responsabilidade de
    quem chamou (o nó do grafo — ver `orchestrator/graphs/intake.py::_call_structured`),
    nunca do `LLMClient`: isso mantém a falha de validação um erro explícito
    e testável do domínio (mesmo princípio de `PromptLoadError`, não um
    detalhe escondido dentro do client.
    """

    raw_output: dict[str, Any]
    model_used: str
    tokens_used: int
    duration_ms: int


class LLMClient(Protocol):
    """Contrato mínimo que qualquer provedor de IA precisa implementar."""

    async def complete(
        self, *, model: str, system_prompt: str, user_input: dict[str, Any]
    ) -> StructuredLLMResult:
        """Executa uma chamada ao modelo e retorna a saída bruta (ainda não validada).

        Args:
            model: Identificador do modelo — nunca hardcoded no nó chamador,
                sempre vindo de uma constante/config em `app/core/config.py`.
            system_prompt: Prompt final já montado por
                `app.core.prompts.load_prompt_bundle` (as 4 camadas compostas).
            user_input: Fatos do caso relevantes para esta chamada — nunca
                inclui segredos, API keys, nem repete o `system_prompt`.

        Returns:
            `StructuredLLMResult` com a saída bruta (`raw_output`, um dict —
            ainda sem validação de schema), tokens consumidos e duração.
        """
        ...


class LLMNotConfiguredError(Exception):
    """Levantada quando um nó precisa de um `LLMClient` mas nenhum foi
    injetado via `Runtime[IntakeContext]` — nunca cai para um provedor real
    "por padrão" silenciosamente (mesmo princípio de falha explícita usado em
    `app/core/prompts.py::PromptLoadError`)."""
