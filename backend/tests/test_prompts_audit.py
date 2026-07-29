"""Testes de composição/versão/hash/segurança do carregador de prompts
(CLAUDE.md, seção 11) — complementa tests/test_prompts.py.
"""

import hashlib

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.config import settings
from app.core.db import async_session_factory
from app.core.prompts import (
    PromptFrontMatter,
    PromptLoadError,
    build_prompt_audit_metadata,
    load_agent_document,
    load_prompt,
    load_prompt_bundle,
)
from app.models.audit_log import AuditLog
from tests.conftest import _SET_TENANT_GUC, TenantFixture


def test_load_prompt_bundle_returns_all_four_layers_in_order() -> None:
    bundle = load_prompt_bundle("digital", "intake", "coordinator")

    assert [layer.layer for layer in bundle.layers] == [
        "base",
        "output_format",
        "squad_context",
        "agent",
    ]


def test_load_prompt_bundle_text_matches_load_prompt() -> None:
    bundle = load_prompt_bundle("digital", "intake", "triage")
    assert bundle.text == load_prompt("digital", "intake", "triage")


def test_base_layer_has_no_version_but_has_hash() -> None:
    bundle = load_prompt_bundle("digital", "intake", "coordinator")
    base_layer = next(layer for layer in bundle.layers if layer.layer == "base")

    assert base_layer.version is None
    assert len(base_layer.content_hash) == 64


def test_agent_layer_hash_is_sha256_of_the_raw_file_content() -> None:
    document = load_agent_document("digital", "intake", "coordinator")
    path = settings.prompts_dir_path / "digital" / "intake" / "coordinator.md"
    expected = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()

    assert document.content_hash == expected


def test_hash_is_deterministic_across_calls() -> None:
    first = load_agent_document("digital", "evidence", "documental")
    second = load_agent_document("digital", "evidence", "documental")
    assert first.content_hash == second.content_hash


def test_different_agents_produce_different_hashes() -> None:
    coordinator = load_agent_document("digital", "intake", "coordinator")
    triage = load_agent_document("digital", "intake", "triage")
    assert coordinator.content_hash != triage.content_hash


def test_layer_paths_are_relative_never_absolute() -> None:
    bundle = load_prompt_bundle("digital", "intake", "coordinator")
    for layer in bundle.layers:
        assert not layer.path.startswith("/")
    agent_layer = next(layer for layer in bundle.layers if layer.layer == "agent")
    assert agent_layer.path == "digital/intake/coordinator.md"


@pytest.mark.parametrize(
    "agent",
    [
        "../../../etc/passwd",
        "../_squad",
        "/etc/passwd",
        "coordinator/../../../evil",
        "Coordinator",  # maiúscula não é um identificador válido
        "coordinator.md",  # extensão não faz parte do identificador
        "",
    ],
)
def test_load_agent_document_rejects_path_traversal_and_invalid_identifiers(agent: str) -> None:
    with pytest.raises(PromptLoadError):
        load_agent_document("digital", "intake", agent)


def test_load_prompt_rejects_unknown_squad() -> None:
    with pytest.raises(PromptLoadError):
        load_prompt("outro-squad", "intake", "coordinator")


def test_load_prompt_rejects_unknown_module() -> None:
    with pytest.raises(PromptLoadError):
        load_prompt("digital", "modulo-que-nao-existe", "coordinator")


def test_load_prompt_bundle_rejects_squad_path_traversal() -> None:
    with pytest.raises(PromptLoadError):
        load_prompt_bundle("../../etc", "intake", "coordinator")


def test_front_matter_rejects_non_semver_version() -> None:
    with pytest.raises(ValidationError):
        PromptFrontMatter(
            version="v1",
            squad="digital",
            module="intake",
            agent="coordinator",
            last_updated="2026-07-28",
        )


def test_front_matter_accepts_strict_semver() -> None:
    front_matter = PromptFrontMatter(
        version="1.2.10",
        squad="digital",
        module="intake",
        agent="coordinator",
        last_updated="2026-07-28",
    )
    assert front_matter.version == "1.2.10"


def test_build_prompt_audit_metadata_has_version_and_hash_per_layer() -> None:
    bundle = load_prompt_bundle("digital", "intake", "coordinator")
    metadata = build_prompt_audit_metadata(bundle)

    assert set(metadata.keys()) == {"prompts"}
    assert len(metadata["prompts"]) == 4
    layer_by_name = {entry["layer"]: entry for entry in metadata["prompts"]}
    assert layer_by_name["base"]["version"] is None
    assert layer_by_name["agent"]["version"] == "1.0.0"
    assert layer_by_name["agent"]["path"] == "digital/intake/coordinator.md"
    assert len(layer_by_name["agent"]["content_hash"]) == 64


async def test_prompt_audit_metadata_persists_versions_and_hashes_in_audit_log(
    tenant_with_case: TenantFixture,
) -> None:
    """Prova de ponta a ponta de "registrar no audit_log as versões e hashes
    dos prompts utilizados": um nó de grafo chamaria load_prompt_bundle,
    montaria a auditoria com build_prompt_audit_metadata e persistiria via
    audit_entry_to_orm — exatamente como create_audit_entry/audit_entry_to_orm
    já fazem para qualquer outra ação (app/core/audit.py).
    """
    bundle = load_prompt_bundle("digital", "intake", "triage")
    metadata = build_prompt_audit_metadata(bundle)

    entry = create_audit_entry(
        actor_id="triage",
        action="montou o prompt final do agente de triagem",
        module="intake",
        input_data={"case_id": str(tenant_with_case.case_id)},
        output_data={"prompt_length": len(bundle.text)},
        model_used="n/a",
        tokens_used=0,
        duration_ms=1,
        actor="system",
        metadata=metadata,
    )

    async with async_session_factory() as session:
        await session.execute(text(_SET_TENANT_GUC), {"t": str(tenant_with_case.tenant_id)})
        orm_entry = audit_entry_to_orm(
            entry, tenant_id=tenant_with_case.tenant_id, case_id=tenant_with_case.case_id
        )
        session.add(orm_entry)
        await session.commit()

        stored = await session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_with_case.tenant_id,
                AuditLog.action == "montou o prompt final do agente de triagem",
            )
        )
        assert stored is not None
        stored_layers = {layer["layer"]: layer for layer in stored.metadata_["prompts"]}
        assert stored_layers["agent"]["path"] == "digital/intake/triage.md"
        assert stored_layers["agent"]["version"] == "1.0.0"
        assert len(stored_layers["squad_context"]["content_hash"]) == 64
