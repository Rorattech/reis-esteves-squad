"""Testes de backend/app/core/prompts.py (CLAUDE.md, seção 11)."""

import pytest

from app.core.prompts import PromptLoadError, load_agent_document, load_prompt

_ALL_AGENTS = [
    ("intake", "coordinator"),
    ("intake", "triage"),
    ("evidence", "documental"),
    ("evidence", "specialist"),
    ("research", "legislation"),
    ("research", "jurisprudence"),
    ("research", "doctrine"),
    ("strategy", "strategist"),
    ("drafting", "skeleton"),
    ("drafting", "writer"),
    ("review", "reviewer"),
    ("review", "learning"),
]


@pytest.mark.parametrize("module, agent", _ALL_AGENTS)
def test_every_digital_agent_prompt_loads_with_required_sections(module: str, agent: str) -> None:
    document = load_agent_document("digital", module, agent)

    assert document.front_matter.squad == "digital"
    assert document.front_matter.module == module
    assert document.front_matter.agent == agent
    assert "## Papel" in document.body
    assert "## Inputs Necessários" in document.body
    assert "## Restrições" in document.body
    assert "## Output Esperado" in document.body


@pytest.mark.parametrize("module, agent", _ALL_AGENTS)
def test_load_prompt_composes_base_and_output_format_and_squad_and_agent(
    module: str, agent: str
) -> None:
    full_prompt = load_prompt("digital", module, agent)

    assert "Base Squad — Reis Esteves Advocacia" in full_prompt
    assert "Formato de Output Padrão — Reis Esteves Advocacia" in full_prompt
    assert "Contexto do Squad Digital — Reis Esteves Advocacia" in full_prompt


def test_load_agent_document_missing_file_raises() -> None:
    with pytest.raises(PromptLoadError):
        load_agent_document("digital", "intake", "agente_que_nao_existe")


def test_load_agent_document_wrong_directory_raises_not_found() -> None:
    # skeleton pertence a drafting (CLAUDE.md, seção 14) — não existe em strategy/.
    with pytest.raises(PromptLoadError):
        load_agent_document("digital", "strategy", "skeleton")
