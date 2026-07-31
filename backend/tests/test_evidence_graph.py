"""Testes unitários dos nós do módulo Evidence (Fase 3.3) com stub de LLM.

Nenhum provedor de IA real é chamado (CLAUDE.md, seção 15). Cobertura do
roadmap 3.3: rastreabilidade de todo achado, distinção fato/inferência/
lacuna, ausência de conteúdo inventado e aguardo obrigatório de revisão
humana ao final.
"""

import pytest
from langgraph.runtime import Runtime

from orchestrator.graphs.evidence import (
    EvidenceContext,
    EvidenceGraphValidationError,
    EvidenceTraceabilityError,
    LLMOutputValidationError,
    bootstrap_evidence,
    build_evidence_graph,
    documental,
    specialist,
)
from orchestrator.state import CaseState, EvidenceRecord
from tests.llm_stubs import StubLLMClient

_EVIDENCE_A = "11111111-1111-1111-1111-111111111111"
_EVIDENCE_B = "22222222-2222-2222-2222-222222222222"

_DOCUMENTAL_OK = {
    "items": [
        {
            "evidence_id": _EVIDENCE_A,
            "evidence_type": "conversation",
            "description": "Conversa de WhatsApp com o golpista negociando o falso produto.",
            "relevance": "high",
            "legal_use": "Comprova a negociação e a promessa de entrega.",
        },
        {
            "evidence_id": _EVIDENCE_B,
            "evidence_type": "payment_receipt",
            "description": "Comprovante PIX de R$ 1.200,00 para conta de terceiro.",
            "relevance": "high",
            "legal_use": "Comprova o dano material e o beneficiário da fraude.",
        },
    ],
    "findings": [
        {
            "source_evidence_id": _EVIDENCE_B,
            "category": "fact",
            "evidence_type": "payment_receipt",
            "summary": "Transferência PIX de R$ 1.200,00 em 12/07/2026.",
            "relevance": "high",
            "suggested_use": "Base do pedido de dano material.",
            "gaps": [],
            "confidence": 0.9,
        },
        {
            "source_evidence_id": None,
            "category": "missing_info",
            "evidence_type": "document",
            "summary": "Não há boletim de ocorrência anexado.",
            "relevance": "medium",
            "suggested_use": "Solicitar BO ao cliente antes da petição.",
            "gaps": ["boletim de ocorrência"],
            "confidence": 1.0,
        },
    ],
    "missing_documents": ["Boletim de ocorrência", "URL do perfil do golpista"],
    "rationale": "Inventário construído apenas a partir dos textos extraídos.",
}

_SPECIALIST_OK = {
    "platform_context": "O Marketplace intermedia a transação e retém o histórico do anúncio.",
    "platform_failure": "O perfil recém-criado não foi sinalizado pelos filtros da plataforma.",
    "report_mechanism_analysis": "Denúncia in-app disponível, sem resposta em 15 dias.",
    "preservation_recommendations": [
        "Preservar a URL do anúncio via ata notarial.",
        "Solicitar logs de acesso à plataforma.",
    ],
    "hypotheses": ["Perfil fantasma operado com conta laranja para receber o PIX."],
    "findings": [
        {
            "source_evidence_id": _EVIDENCE_A,
            "category": "inference",
            "evidence_type": "conversation",
            "summary": "Padrão de pressão por urgência típico de vendedor fantasma.",
            "relevance": "medium",
            "suggested_use": "Reforça a caracterização da fraude na narrativa.",
            "gaps": [],
            "confidence": 0.7,
        }
    ],
    "rationale": "Leitura técnica baseada nos achados documentais.",
}


def _state(records: list[EvidenceRecord] | None = None) -> CaseState:
    return CaseState(
        case_id="33333333-3333-3333-3333-333333333333",
        tenant_id="44444444-4444-4444-4444-444444444444",
        narrative="Comprei um produto no marketplace e nunca recebi.",
        platform="facebook_marketplace",
        fraud_type="marketplace",
        urgency="high",
        area="digital",
        matter="Fraude em marketplace",
        intake_outcome=None,
        missing_information=[],
        out_of_scope_reason=None,
        documents_requested=["Comprovante de endereço"],
        evidence_records=(
            records
            if records is not None
            else [
                EvidenceRecord(
                    evidence_id=_EVIDENCE_A,
                    filename="conversa.txt",
                    mime_type="text/plain",
                    processing_status="processed",
                    extracted_text="Conversa: prometo entregar amanhã, faca o PIX.",
                    extraction_confidence=1.0,
                    extraction_limitations="Decodificação direta.",
                ),
                EvidenceRecord(
                    evidence_id=_EVIDENCE_B,
                    filename="comprovante.pdf",
                    mime_type="application/pdf",
                    processing_status="processed",
                    extracted_text="Comprovante PIX R$ 1.200,00.",
                    extraction_confidence=0.95,
                    extraction_limitations="Texto nativo do PDF.",
                ),
            ]
        ),
        evidence_inventory=[],
        evidence_findings=[],
        specialist_assessment=None,
        evidence_outcome=None,
        legal_sources=[],
        strategy_memo=None,
        draft_petition=None,
        human_approval_required=False,
        human_approval_status="na",
        approved_by=None,
        approved_at=None,
        audit_trail=[],
        current_module="evidence",
        status="active",
    )


def _runtime(stub: StubLLMClient) -> Runtime[EvidenceContext]:
    return Runtime(context=EvidenceContext(llm_client=stub))


async def test_full_graph_builds_traceable_inventory_and_awaits_human_review() -> None:
    stub = StubLLMClient(responses=[_DOCUMENTAL_OK, _SPECIALIST_OK])
    graph = build_evidence_graph()
    result = await graph.ainvoke(_state(), context=EvidenceContext(llm_client=stub))

    # Inventário rastreável: um item por evidência analisada, com o texto
    # extraído vindo do registro original — nunca inventado.
    assert len(result["evidence_inventory"]) == 2
    by_id = {item.evidence_id: item for item in result["evidence_inventory"]}
    assert by_id[_EVIDENCE_A].file_reference == "conversa.txt"
    assert by_id[_EVIDENCE_B].extracted_text == "Comprovante PIX R$ 1.200,00."

    # Achados dos dois agentes, todos pendentes de revisão humana.
    agents = {finding.agent for finding in result["evidence_findings"]}
    assert agents == {"documental", "specialist"}
    assert all(f.status == "DRAFT_PENDING_REVIEW" for f in result["evidence_findings"])
    assert all(f.requires_human_review for f in result["evidence_findings"])

    # Fato/inferência/lacuna distinguidos; lacuna é o único sem origem.
    categories = {finding.category for finding in result["evidence_findings"]}
    assert categories == {"fact", "inference", "missing_info"}
    for finding in result["evidence_findings"]:
        if finding.category == "missing_info":
            assert finding.source_evidence_id is None
        else:
            assert finding.source_evidence_id in (_EVIDENCE_A, _EVIDENCE_B)

    # Documentos faltantes somados ao checklist já existente.
    assert "Boletim de ocorrência" in result["documents_requested"]
    assert "Comprovante de endereço" in result["documents_requested"]

    # Leitura técnica presente e igualmente pendente.
    assert result["specialist_assessment"] is not None
    assert result["specialist_assessment"].status == "DRAFT_PENDING_REVIEW"

    # O módulo nunca conclui sozinho: fica aguardando revisão humana.
    assert result["evidence_outcome"] == "awaiting_human_review"
    assert result["human_approval_required"] is True
    assert result["human_approval_status"] == "pending"

    # Auditoria: bootstrap (system) + documental + specialist (agents).
    actors = [entry.actor_id for entry in result["audit_trail"]]
    assert actors == ["system", "documental", "specialist"]


async def test_bootstrap_rejects_case_without_evidence() -> None:
    with pytest.raises(EvidenceGraphValidationError, match="Nenhuma evidência"):
        bootstrap_evidence(_state(records=[]))


async def test_documental_rejects_finding_pointing_to_unknown_evidence() -> None:
    tampered = {
        **_DOCUMENTAL_OK,
        "findings": [
            {
                **_DOCUMENTAL_OK["findings"][0],
                "source_evidence_id": "99999999-9999-9999-9999-999999999999",
            }
        ],
    }
    stub = StubLLMClient(responses=[tampered])
    with pytest.raises(EvidenceTraceabilityError, match="inexistente"):
        await documental(_state(), _runtime(stub))


async def test_documental_rejects_fact_without_source() -> None:
    tampered = {
        **_DOCUMENTAL_OK,
        "findings": [{**_DOCUMENTAL_OK["findings"][0], "source_evidence_id": None}],
    }
    stub = StubLLMClient(responses=[tampered])
    with pytest.raises(EvidenceTraceabilityError, match="sem evidência de origem"):
        await documental(_state(), _runtime(stub))


async def test_documental_rejects_invented_inventory_item() -> None:
    tampered = {
        **_DOCUMENTAL_OK,
        "items": [
            {**_DOCUMENTAL_OK["items"][0], "evidence_id": "99999999-9999-9999-9999-999999999999"}
        ],
    }
    stub = StubLLMClient(responses=[tampered])
    with pytest.raises(EvidenceTraceabilityError, match="inventar provas"):
        await documental(_state(), _runtime(stub))


async def test_invalid_llm_output_is_never_swallowed() -> None:
    stub = StubLLMClient(responses=[{"items": "isso não é uma lista"}])
    with pytest.raises(LLMOutputValidationError):
        await documental(_state(), _runtime(stub))


async def test_specialist_findings_are_validated_too() -> None:
    tampered = {
        **_SPECIALIST_OK,
        "findings": [
            {
                **_SPECIALIST_OK["findings"][0],
                "source_evidence_id": "99999999-9999-9999-9999-999999999999",
            }
        ],
    }
    stub = StubLLMClient(responses=[tampered])
    state = _state()
    with pytest.raises(EvidenceTraceabilityError, match="specialist"):
        await specialist(state, _runtime(stub))
