"""Utilitário central de auditoria (CLAUDE.md, seção 10).

Todo nó de grafo LangGraph deve chamar `create_audit_entry(...)` antes de
retornar, para anexar o registro ao `audit_trail` do CaseState — nunca grave
diretamente em AuditLog (SQLAlchemy) a partir de um nó; a persistência em
Postgres é responsabilidade de quem grava o checkpoint do CaseState
(orchestrator/checkpoints.py), usando `audit_entry_to_orm` abaixo para
converter cada AuditEntry do trail em uma linha de audit_logs.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.models.audit_log import AuditLog
from app.models.enums import AuditActor
from app.models.enums import ModuleName as DbModuleName
from orchestrator.state import AuditEntry
from orchestrator.state import ModuleName as GraphModuleName


def _stable_hash(data: Any) -> str:
    """Calcula o SHA-256 determinístico de um dado, para uso em input_hash/output_hash.

    Nunca persiste o conteúdo em claro (CLAUDE.md, seção 12 — nunca logar
    conteúdo de documentos/dados pessoais): apenas o hash é armazenado.

    Args:
        data: Dado a ser hasheado — dict, lista, BaseModel.model_dump(), str, etc.

    Returns:
        Hash SHA-256 em hexadecimal (64 caracteres).
    """
    serialized = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_audit_entry(
    actor_id: str,
    action: str,
    module: GraphModuleName,
    input_data: Any,
    output_data: Any,
    model_used: str,
    tokens_used: int,
    duration_ms: int,
    actor: Literal["system", "agent", "human"] = "agent",
    metadata: dict[str, Any] | None = None,
) -> AuditEntry:
    """Cria uma entrada de auditoria imutável para uma ação de um nó do grafo.

    Args:
        actor_id: Nome do agente (ex.: "coordinator") ou ID do usuário humano
            que executou a ação.
        action: Descrição curta da ação realizada (ex.: "classificou a plataforma ré").
        module: Um dos 6 módulos LangGraph onde a ação ocorreu.
        input_data: Entrada recebida pelo nó — nunca persistida em claro, apenas hasheada.
        output_data: Saída gerada pelo nó — nunca persistida em claro, apenas hasheada.
        model_used: Identificador do modelo de IA usado (via constante de core/config.py).
        tokens_used: Total de tokens consumidos na chamada ao modelo.
        duration_ms: Tempo de execução do nó em milissegundos.
        actor: Quem executou a ação — "system", "agent" ou "human" (padrão "agent").
        metadata: Dados adicionais livres associados à ação.

    Returns:
        AuditEntry pronta para ser anexada a `CaseState["audit_trail"]`.
    """
    return AuditEntry(
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        actor_id=actor_id,
        action=action,
        module=module,
        input_hash=_stable_hash(input_data),
        output_hash=_stable_hash(output_data),
        model_used=model_used,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        metadata=metadata or {},
    )


def audit_entry_to_orm(
    entry: AuditEntry,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
) -> AuditLog:
    """Converte uma AuditEntry (CaseState) em uma linha persistível de audit_logs.

    `entry.actor_id` guarda o nome do agente/usuário; `agent_name` na tabela
    replica o mesmo valor — são o mesmo dado sob duas colunas porque
    `AuditLog.actor_id` é genérico (CLAUDE.md, seção 10) enquanto
    `AuditLog.agent_name` é o nome específico do agente dentro do módulo.

    Args:
        entry: Entrada de auditoria gerada por `create_audit_entry`.
        tenant_id: Tenant dono do caso — nunca inferido do conteúdo da entrada.
        case_id: Caso ao qual esta ação pertence.

    Returns:
        Instância de AuditLog pronta para `session.add(...)` — o chamador é
        responsável pela sessão escopada por tenant (CLAUDE.md, seção 7).
    """
    return AuditLog(
        tenant_id=tenant_id,
        case_id=case_id,
        actor=AuditActor(entry.actor),
        actor_id=entry.actor_id,
        action=entry.action,
        module=DbModuleName(entry.module),
        input_hash=entry.input_hash,
        output_hash=entry.output_hash,
        agent_name=entry.actor_id,
        model_used=entry.model_used,
        tokens_used=entry.tokens_used,
        duration_ms=entry.duration_ms,
        metadata_=entry.metadata,
    )
