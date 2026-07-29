"""Modelo de checkpoint do CaseState — snapshot do estado do grafo LangGraph
entre transições de nó (orchestrator/checkpoints.py, docs/architecture.md,
seção 3.3).

Tabela própria (não o checkpointer nativo do LangGraph): toda tabela do
projeto exige tenant_id + RLS (CLAUDE.md, seção 7), e o checkpointer padrão do
LangGraph não oferece esse controle — ver orchestrator/checkpoints.py.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class CaseCheckpoint(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Snapshot imutável do CaseState em um passo específico do grafo.

    `step` é monotonicamente crescente por caso — o checkpoint mais recente é
    sempre o de maior `step`. A aplicação nunca faz UPDATE aqui, apenas INSERT
    (mesmo princípio de audit_logs).
    """

    __tablename__ = "case_checkpoints"
    __table_args__ = (UniqueConstraint("case_id", "step", name="uq_case_checkpoints_case_id_step"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    current_module: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    tenant: Mapped["Tenant"] = relationship()
    case: Mapped["Case"] = relationship()
