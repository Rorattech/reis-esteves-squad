"""Modelo do relato inicial (intake) de um caso — módulo LangGraph intake.

Um caso tem no máximo um registro de intake (relação 1:1 via UniqueConstraint
em case_id): o relato é editável pelo advogado até a triagem ser concluída,
não versionado nesta camada de domínio (histórico de decisões de revisão
humana é responsabilidade do audit_log, ver CLAUDE.md, seção 10).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class CaseIntake(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Relato inicial estruturado de um caso (Fase 2 — Intake e Roteamento).

    Guarda apenas o texto livre do relato e os campos estruturados informados
    no primeiro contato — nunca os arquivos de evidência em si (isso é a Fase
    3, Evidências: ver docs/roadmap_mvp_squad_digital.md).
    """

    __tablename__ = "case_intakes"
    __table_args__ = (UniqueConstraint("case_id", name="uq_case_intakes_case_id"),)

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
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_loss_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    incident_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    has_police_report: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    claimed_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    pending_information: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship()
    case: Mapped["Case"] = relationship(back_populates="intake")
