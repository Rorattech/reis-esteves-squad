"""Carregador versionado de prompts (CLAUDE.md, seção 11).

Monta o prompt final de um agente na ordem obrigatória: `_shared/_base.md`
(sem front matter) → `_shared/output_format.md` → `<squad>/_squad.md` →
`<squad>/<módulo>/<agente>.md`. Nenhum nó de grafo deve montar prompt inline
no código Python nem ler arquivos de prompts/ diretamente — sempre via
`load_prompt(...)` (ou `load_prompt_bundle(...)` quando o chamador precisar
registrar versão/hash em audit_log).

Segurança: `squad`, `module` e `agent` nunca podem ser um caminho de arquivo
vindo diretamente do usuário (CLAUDE.md, seção 11) — `_validate_identifiers`
restringe `squad`/`module` a allowlists fechadas e `agent` a um padrão
snake_case sem separador de diretório, e `_resolve_agent_path` confirma que o
caminho final resolvido continua dentro de `settings.prompts_dir_path` antes
de qualquer leitura de disco.

Ver docs/prompt_loader.md para a documentação completa da API interna.
"""

import hashlib
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.core.config import settings

_FRONT_MATTER_DELIMITER = "---"
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

Squad = Literal["digital"]
"""Squads suportados no MVP (CLAUDE.md, seção 11) — "Atualmente existe apenas
o squad `digital`"."""

Module = Literal["intake", "evidence", "research", "strategy", "drafting", "review"]
"""Um dos 6 módulos LangGraph (CLAUDE.md, seção 14)."""

_ALLOWED_SQUADS: frozenset[str] = frozenset(("digital",))
_ALLOWED_MODULES: frozenset[str] = frozenset(
    ("intake", "evidence", "research", "strategy", "drafting", "review")
)

PromptLayer = Literal["base", "output_format", "squad_context", "agent"]


class PromptLoadError(Exception):
    """Levantada quando um arquivo de prompt não existe, está malformado,
    tem front matter inconsistente com o que foi pedido, ou quando squad/
    module/agent não são identificadores válidos (CLAUDE.md, seção 11)."""


class PromptFrontMatter(BaseModel):
    """Cabeçalho YAML obrigatório de todo prompt, exceto `_base.md` (CLAUDE.md, seção 11)."""

    version: str
    squad: str
    module: str
    agent: str
    last_updated: date

    @field_validator("version")
    @classmethod
    def _version_must_be_semver(cls, value: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError(
                f"version deve seguir semver estrito (ex.: 1.0.0), recebido: {value!r}"
            )
        return value


class PromptDocument(BaseModel):
    """Um arquivo de prompt já parseado: front matter + corpo + proveniência."""

    front_matter: PromptFrontMatter
    body: str
    path: str
    """Caminho relativo a `settings.prompts_dir_path` — nunca absoluto (evita
    vazar a estrutura de diretórios do host em audit_log/logs)."""
    content_hash: str
    """SHA-256 (hex) do conteúdo bruto do arquivo (front matter + corpo),
    para registro em audit_log — ver `PromptLayerInfo`/`build_prompt_audit_metadata`."""


class PromptLayerInfo(BaseModel):
    """Proveniência de uma das 4 camadas usadas para montar um prompt final.

    Formato pronto para virar `metadata` de um `AuditEntry`
    (CLAUDE.md, seção 10) — ver `build_prompt_audit_metadata`.
    """

    layer: PromptLayer
    path: str
    version: str | None
    """None apenas para a camada "base" (`_base.md`) — única exceção do
    projeto sem front matter (CLAUDE.md, seção 11)."""
    content_hash: str


class PromptBundle(BaseModel):
    """Prompt final composto, com a proveniência (versão + hash) de cada camada."""

    text: str
    layers: list[PromptLayerInfo]

    @model_validator(mode="after")
    def _must_have_all_layers(self) -> "PromptBundle":
        found = {layer.layer for layer in self.layers}
        expected = {"base", "output_format", "squad_context", "agent"}
        if found != expected:
            raise ValueError(f"PromptBundle incompleto: esperado {expected}, obtido {found}")
        return self


def _hash_content(raw: str) -> str:
    """SHA-256 (hex) do conteúdo bruto de um arquivo de prompt."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _relative_path(path: Path) -> str:
    return path.resolve().relative_to(settings.prompts_dir_path.resolve()).as_posix()


def _validate_identifiers(squad: str, module: str, agent: str) -> None:
    """Garante que squad/module/agent são identificadores fechados, nunca um
    caminho de arquivo vindo do usuário (CLAUDE.md, seção 11).

    Args:
        squad: Squad solicitado.
        module: Módulo solicitado.
        agent: Agente solicitado.

    Raises:
        PromptLoadError: Se squad/module não estiverem na allowlist, ou se
            agent não for um identificador snake_case simples (sem `/`, `..`
            ou caracteres fora de `[a-z0-9_]`).
    """
    if squad not in _ALLOWED_SQUADS:
        raise PromptLoadError(
            f"Squad desconhecido: {squad!r} — squads suportados: {sorted(_ALLOWED_SQUADS)}"
        )
    if module not in _ALLOWED_MODULES:
        raise PromptLoadError(
            f"Módulo desconhecido: {module!r} — módulos suportados: {sorted(_ALLOWED_MODULES)}"
        )
    if not _IDENTIFIER_PATTERN.fullmatch(agent):
        raise PromptLoadError(
            f"Nome de agente inválido: {agent!r} — use apenas letras minúsculas, "
            "dígitos e underscore (sem separador de diretório)."
        )


def _resolve_agent_path(squad: str, module: str, agent: str) -> Path:
    """Resolve o caminho do prompt de um agente, validando identificadores e
    confirmando que o resultado continua dentro de `prompts_dir_path`.

    A checagem de identificadores por si só já impede um `agent` como
    `"../../etc/passwd"`, mas o `is_relative_to` abaixo é uma segunda camada
    de defesa contra qualquer allowlist futura menos restritiva.
    """
    _validate_identifiers(squad, module, agent)
    base_dir = settings.prompts_dir_path.resolve()
    path = (base_dir / squad / module / f"{agent}.md").resolve()
    if not path.is_relative_to(base_dir):
        raise PromptLoadError(f"Caminho de prompt fora do diretório permitido: {path}")
    return path


def _read_raw(path: Path) -> str:
    if not path.is_file():
        raise PromptLoadError(f"Arquivo de prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def _parse_document(path: Path) -> PromptDocument:
    """Separa front matter YAML e corpo markdown de um arquivo de prompt.

    Args:
        path: Caminho do arquivo `.md` a ser lido.

    Returns:
        PromptDocument com o front matter validado, o corpo (markdown, sem o
        bloco de front matter), o caminho relativo e o hash do conteúdo bruto.

    Raises:
        PromptLoadError: Se o arquivo não existir, não tiver front matter no
            formato esperado, ou o front matter for inválido (versão fora do
            padrão semver incluída).
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

    return PromptDocument(
        front_matter=front_matter,
        body=body,
        path=_relative_path(path),
        content_hash=_hash_content(raw),
    )


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
def _load_base_layer() -> PromptLayerInfo:
    """Carrega prompts/_shared/_base.md — única exceção sem front matter (CLAUDE.md, seção 11)."""
    path = settings.prompts_dir_path / "_shared" / "_base.md"
    raw = _read_raw(path)
    return PromptLayerInfo(
        layer="base", path=_relative_path(path), version=None, content_hash=_hash_content(raw)
    )


@lru_cache(maxsize=1)
def _load_base_prompt() -> str:
    path = settings.prompts_dir_path / "_shared" / "_base.md"
    return _read_raw(path).strip("\n")


@lru_cache(maxsize=1)
def _load_output_format_document() -> PromptDocument:
    path = settings.prompts_dir_path / "_shared" / "output_format.md"
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad="shared", module="all", agent="output_format")
    return document


@lru_cache(maxsize=32)
def _load_squad_context_document(squad: str) -> PromptDocument:
    path = settings.prompts_dir_path / squad / "_squad.md"
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad=squad, module="all", agent="squad_context")
    return document


def load_agent_document(squad: str, module: str, agent: str) -> PromptDocument:
    """Carrega e valida o arquivo de prompt de um agente específico, sem montar o prompt final.

    Útil para inspecionar/validar metadados (versão, data, hash) de um
    prompt isoladamente — para montar o prompt completo pronto para uso no
    LLM, use `load_prompt` ou `load_prompt_bundle`.

    Args:
        squad: Squad do agente (ex.: "digital").
        module: Um dos 6 módulos LangGraph (ex.: "intake").
        agent: Nome do agente dentro do módulo (ex.: "coordinator").

    Returns:
        PromptDocument com front matter validado e o corpo em markdown.

    Raises:
        PromptLoadError: Se squad/module/agent não forem identificadores
            válidos, se o arquivo não existir, ou se o front matter for
            inválido ou inconsistente com os parâmetros pedidos.
    """
    path = _resolve_agent_path(squad, module, agent)
    document = _parse_document(path)
    _validate_front_matter(document, path=path, squad=squad, module=module, agent=agent)
    return document


def load_prompt_bundle(squad: Squad, module: Module, agent: str) -> PromptBundle:
    """Monta o prompt final de um agente e a proveniência de cada camada usada.

    Ordem de composição: `_shared/_base.md` → `_shared/output_format.md` →
    `<squad>/_squad.md` → `<squad>/<module>/<agent>.md` (CLAUDE.md, seção 11).

    Use esta função (em vez de `load_prompt`) quando o chamador for um nó de
    grafo que precisa registrar versão/hash dos prompts em audit_log — passe
    `build_prompt_audit_metadata(bundle)` como `metadata=` de
    `create_audit_entry(...)` (CLAUDE.md, seção 10).

    Args:
        squad: Squad do agente. Atualmente só "digital" existe.
        module: Um dos 6 módulos LangGraph.
        agent: Nome do agente dentro do módulo (ex.: "coordinator", "triage").

    Returns:
        PromptBundle com o texto final e a proveniência de cada uma das 4 camadas.

    Raises:
        PromptLoadError: Se squad/module/agent não forem identificadores
            válidos, se algum dos 4 arquivos não existir, ou se algum front
            matter for inválido/inconsistente.
    """
    _validate_identifiers(squad, module, agent)

    base_layer = _load_base_layer()
    output_format_doc = _load_output_format_document()
    squad_doc = _load_squad_context_document(squad)
    agent_doc = load_agent_document(squad, module, agent)

    layers = [
        base_layer,
        PromptLayerInfo(
            layer="output_format",
            path=output_format_doc.path,
            version=output_format_doc.front_matter.version,
            content_hash=output_format_doc.content_hash,
        ),
        PromptLayerInfo(
            layer="squad_context",
            path=squad_doc.path,
            version=squad_doc.front_matter.version,
            content_hash=squad_doc.content_hash,
        ),
        PromptLayerInfo(
            layer="agent",
            path=agent_doc.path,
            version=agent_doc.front_matter.version,
            content_hash=agent_doc.content_hash,
        ),
    ]
    sections = [_load_base_prompt(), output_format_doc.body, squad_doc.body, agent_doc.body]
    text = "\n\n".join(section for section in sections if section)

    return PromptBundle(text=text, layers=layers)


def load_prompt(squad: Squad, module: Module, agent: str) -> str:
    """Monta o prompt final de um agente, na ordem obrigatória do CLAUDE.md §11.

    Atalho para `load_prompt_bundle(...).text` — use `load_prompt_bundle`
    diretamente quando precisar registrar versão/hash em audit_log.

    Args:
        squad: Squad do agente. Atualmente só "digital" existe (CLAUDE.md, seção 11).
        module: Um dos 6 módulos LangGraph.
        agent: Nome do agente dentro do módulo (ex.: "coordinator", "triage").

    Returns:
        Prompt final, pronto para ser enviado ao modelo de IA.

    Raises:
        PromptLoadError: Se squad/module/agent não forem identificadores
            válidos, se algum dos 4 arquivos não existir, ou se algum front
            matter for inválido/inconsistente.
    """
    return load_prompt_bundle(squad, module, agent).text


def build_prompt_audit_metadata(bundle: PromptBundle) -> dict[str, Any]:
    """Converte um `PromptBundle` no formato de `metadata` de um `AuditEntry`.

    Registra, para cada uma das 4 camadas usadas, o caminho relativo, a
    versão declarada no front matter (None para `_base.md`) e o hash SHA-256
    do conteúdo — nunca o texto do prompt em si (CLAUDE.md, seção 10, mesmo
    princípio de `core/audit.py`: hash em vez de conteúdo bruto).

    Uso esperado num nó de grafo (módulo 2.3):

        bundle = load_prompt_bundle("digital", "intake", "coordinator")
        entry = create_audit_entry(
            ...,
            metadata=build_prompt_audit_metadata(bundle),
        )

    Args:
        bundle: Retorno de `load_prompt_bundle`.

    Returns:
        Dicionário serializável em JSON, pronto para `create_audit_entry(metadata=...)`.
    """
    return {"prompts": [layer.model_dump(mode="json") for layer in bundle.layers]}
