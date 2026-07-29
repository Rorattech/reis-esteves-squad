"""Carregador versionado de prompts (CLAUDE.md, seção 11).

Monta o prompt final de um agente na ordem obrigatória: `_shared/_base.md`
(sem front matter) → `_shared/output_format.md` → `<squad>/_squad.md` →
`<squad>/<módulo>/<agente>.md`. Nenhum nó de grafo deve montar prompt inline
no código Python nem ler arquivos de prompts/ diretamente — sempre via
`load_prompt(...)`.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

from app.core.config import settings

_FRONT_MATTER_DELIMITER = "---"


class PromptFrontMatter(BaseModel):
    """Cabeçalho YAML obrigatório de todo prompt, exceto `_base.md` (CLAUDE.md, seção 11)."""

    version: str
    squad: str
    module: str
    agent: str
    last_updated: date


class PromptDocument(BaseModel):
    """Um arquivo de prompt já parseado: front matter + corpo em markdown."""

    front_matter: PromptFrontMatter
    body: str


class PromptLoadError(Exception):
    """Levantada quando um arquivo de prompt não existe, está malformado ou
    tem front matter inconsistente com o que foi pedido."""


def _read_raw(path: Path) -> str:
    if not path.is_file():
        raise PromptLoadError(f"Arquivo de prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def _parse_document(path: Path) -> PromptDocument:
    """Separa front matter YAML e corpo markdown de um arquivo de prompt.

    Args:
        path: Caminho do arquivo `.md` a ser lido.

    Returns:
        PromptDocument com o front matter validado e o corpo (markdown, sem
        o bloco de front matter).

    Raises:
        PromptLoadError: Se o arquivo não existir, não tiver front matter no
            formato esperado, ou o front matter for inválido.
    """
    raw = _read_raw(path)
    lines = raw.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIMITER:
        raise PromptLoadError(f"Front matter ausente ou malformado em {path}")

    try:
        closing_index = lines[1:].index(_FRONT_MATTER_DELIMITER) + 1
    except ValueError as exc:
        raise PromptLoadError(f"Front matter sem delimitador de fechamento em {path}") from exc

    raw_front_matter = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :]).strip("\n")

    try:
        parsed = yaml.safe_load(raw_front_matter) or {}
        front_matter = PromptFrontMatter.model_validate(parsed)
    except (yaml.YAMLError, ValidationError) as exc:
        raise PromptLoadError(f"Front matter inválido em {path}: {exc}") from exc

    return PromptDocument(front_matter=front_matter, body=body)


def _validate_front_matter(
    document: PromptDocument, *, path: Path, squad: str, module: str, agent: str
) -> None:
    fm = document.front_matter
    if (fm.squad, fm.module, fm.agent) != (squad, module, agent):
        raise PromptLoadError(
            f"Front matter de {path} não confere com o solicitado: "
            f"esperado squad={squad!r} module={module!r} agent={agent!r}, "
            f"encontrado squad={fm.squad!r} module={fm.module!r} agent={fm.agent!r}"
        )


@lru_cache(maxsize=1)
def _load_base_prompt() -> str:
    """Carrega prompts/_shared/_base.md — única exceção sem front matter (CLAUDE.md, seção 11)."""
    return _read_raw(settings.prompts_dir_path / "_shared" / "_base.md").strip("\n")


@lru_cache(maxsize=1)
def _load_output_format_prompt() -> str:
    path = settings.prompts_dir_path / "_shared" / "output_format.md"
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad="shared", module="all", agent="output_format")
    return document.body


@lru_cache(maxsize=32)
def _load_squad_context_prompt(squad: str) -> str:
    path = settings.prompts_dir_path / squad / "_squad.md"
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad=squad, module="all", agent="squad_context")
    return document.body


def load_agent_document(squad: str, module: str, agent: str) -> PromptDocument:
    """Carrega e valida o arquivo de prompt de um agente específico, sem montar o prompt final.

    Útil para inspecionar/validar metadados (versão, data) de um prompt
    isoladamente — para montar o prompt completo pronto para uso no LLM, use
    `load_prompt`.

    Args:
        squad: Squad do agente (ex.: "digital").
        module: Um dos 6 módulos LangGraph (ex.: "intake").
        agent: Nome do agente dentro do módulo (ex.: "coordinator").

    Returns:
        PromptDocument com front matter validado e o corpo em markdown.

    Raises:
        PromptLoadError: Se o arquivo não existir ou o front matter for
            inválido ou inconsistente com os parâmetros pedidos.
    """
    path = settings.prompts_dir_path / squad / module / f"{agent}.md"
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad=squad, module=module, agent=agent)
    return document


def load_prompt(
    squad: Literal["digital"],
    module: Literal["intake", "evidence", "research", "strategy", "drafting", "review"],
    agent: str,
) -> str:
    """Monta o prompt final de um agente, na ordem obrigatória do CLAUDE.md §11.

    Ordem de composição: `_shared/_base.md` → `_shared/output_format.md` →
    `<squad>/_squad.md` → `<squad>/<module>/<agent>.md`.

    Args:
        squad: Squad do agente. Atualmente só "digital" existe (CLAUDE.md, seção 11).
        module: Um dos 6 módulos LangGraph.
        agent: Nome do agente dentro do módulo (ex.: "coordinator", "triage").

    Returns:
        Prompt final, pronto para ser enviado ao modelo de IA.

    Raises:
        PromptLoadError: Se algum dos 4 arquivos não existir ou tiver front
            matter inválido/inconsistente.
    """
    sections = [
        _load_base_prompt(),
        _load_output_format_prompt(),
        _load_squad_context_prompt(squad),
        load_agent_document(squad, module, agent).body,
    ]
    return "\n\n".join(section for section in sections if section)
