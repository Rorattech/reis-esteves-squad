"""Persistência de checkpoints do CaseState entre transições de nó
(docs/architecture.md, seção 3.3 — "ORQ -- Checkpoint de estado --> DB").

Usa a tabela `case_checkpoints` (backend/app/models/case_checkpoint.py), não o
checkpointer nativo do LangGraph: toda tabela do projeto exige tenant_id + RLS
(CLAUDE.md, seção 7), e o checkpointer padrão do LangGraph gerencia seu
próprio schema, sem esse controle. Quando o fluxo de suspensão/retomada do
grafo (aguardar aprovação humana) for implementado, revisitar essa decisão —
por ora, o router (orchestrator/router.py) decide as transições fora do
grafo, chamando `save_checkpoint`/`load_latest_checkpoint` entre uma
invocação de módulo e outra.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_checkpoint import CaseCheckpoint
from orchestrator.state import (
    AuditEntry,
    CaseState,
    DraftPetition,
    EvidenceItem,
    LegalSource,
    StrategyMemo,
)


def _serialize_state(state: CaseState) -> dict[str, Any]:
    """Converte um CaseState (com sub-modelos Pydantic) em um dict JSON-safe.

    Args:
        state: Estado do caso a ser persistido.

    Returns:
        Dicionário pronto para a coluna JSONB de CaseCheckpoint.state.
    """
    return {
        **state,
        "evidence_inventory": [
            item.model_dump(mode="json") for item in state["evidence_inventory"]
        ],
        "legal_sources": [source.model_dump(mode="json") for source in state["legal_sources"]],
        "strategy_memo": (
            state["strategy_memo"].model_dump(mode="json") if state["strategy_memo"] else None
        ),
        "draft_petition": (
            state["draft_petition"].model_dump(mode="json") if state["draft_petition"] else None
        ),
        "audit_trail": [entry.model_dump(mode="json") for entry in state["audit_trail"]],
    }


def _deserialize_state(raw: dict[str, Any]) -> CaseState:
    """Reconstrói um CaseState a partir do dict JSON armazenado em CaseCheckpoint.state.

    Args:
        raw: Conteúdo bruto da coluna JSONB, como veio do banco.

    Returns:
        CaseState com os sub-modelos Pydantic revalidados.
    """
    return CaseState(
        **{
            **raw,
            "evidence_inventory": [
                EvidenceItem.model_validate(item) for item in raw["evidence_inventory"]
            ],
            "legal_sources": [LegalSource.model_validate(item) for item in raw["legal_sources"]],
            "strategy_memo": (
                StrategyMemo.model_validate(raw["strategy_memo"]) if raw["strategy_memo"] else None
            ),
            "draft_petition": (
                DraftPetition.model_validate(raw["draft_petition"])
                if raw["draft_petition"]
                else None
            ),
            "audit_trail": [AuditEntry.model_validate(item) for item in raw["audit_trail"]],
        }
    )


async def save_checkpoint(session: AsyncSession, state: CaseState) -> CaseCheckpoint:
    """Salva um novo snapshot do CaseState, incrementando o step do caso.

    Args:
        session: Sessão do banco já escopada por tenant (CLAUDE.md, seção 7)
            — nunca chame com uma sessão sem `app.current_tenant` definido.
        state: Estado completo do caso no momento do snapshot.

    Returns:
        O CaseCheckpoint recém-criado (já com `id`/`step` preenchidos).
    """
    tenant_id = uuid.UUID(state["tenant_id"])
    case_id = uuid.UUID(state["case_id"])

    last_step = await session.scalar(
        select(CaseCheckpoint.step)
        .where(CaseCheckpoint.tenant_id == tenant_id, CaseCheckpoint.case_id == case_id)
        .order_by(CaseCheckpoint.step.desc())
        .limit(1)
    )
    checkpoint = CaseCheckpoint(
        tenant_id=tenant_id,
        case_id=case_id,
        step=(last_step or 0) + 1,
        current_module=state["current_module"],
        state=_serialize_state(state),
    )
    session.add(checkpoint)
    await session.flush()
    return checkpoint


async def load_latest_checkpoint(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> CaseState | None:
    """Carrega o snapshot mais recente do CaseState de um caso.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant dono do caso.
        case_id: Caso a ser recuperado.

    Returns:
        O CaseState do checkpoint mais recente, ou None se o caso ainda não
        tiver nenhum checkpoint salvo.
    """
    checkpoint = await session.scalar(
        select(CaseCheckpoint)
        .where(CaseCheckpoint.tenant_id == tenant_id, CaseCheckpoint.case_id == case_id)
        .order_by(CaseCheckpoint.step.desc())
        .limit(1)
    )
    if checkpoint is None:
        return None
    return _deserialize_state(checkpoint.state)
