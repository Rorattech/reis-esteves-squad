"""Modelo de log de auditoria — registro imutável das ações de cada nó do grafo."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import AuditActor, ModuleName

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class AuditLog(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Entrada de auditoria de uma ação executada por um nó do LangGraph.

    Registro imutável (ver CLAUDE.md, seção 10): a aplicação nunca deve fazer
    UPDATE nesta tabela, apenas INSERT. Espelha AuditEntry (orchestrator/state.py)
    no lado do banco — agent_name identifica o agente específico dentro do
    módulo (ex.: "coordinator"), enquanto module identifica um dos 6 módulos
    LangGraph (ex.: "intake").
    """

    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    """Opcional: nulo para ações auditáveis que ainda não pertencem a um caso
    (ex.: cadastro de um cliente antes de qualquer caso ser aberto)."""
    actor: Mapped[AuditActor] = mapped_column(
        db_enum(AuditActor, "audit_actor"),
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[ModuleName] = mapped_column(
        db_enum(ModuleName, "module_name"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Atributo Python não pode se chamar "metadata": colide com o registro de
    # schema herdado de DeclarativeBase.metadata. A coluna no banco chama-se
    # "metadata", igual ao campo AuditEntry.metadata em orchestrator/state.py.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="audit_logs")
    case: Mapped["Case | None"] = relationship(back_populates="audit_logs")
