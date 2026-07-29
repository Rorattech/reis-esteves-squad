"""Modelo do checklist de documentos de um caso (recebido/pendente/dispensado).

Guarda apenas o item do checklist (nome, status, origem) — o arquivo em si
pertence à Fase 3 (Evidências, ver docs/roadmap_mvp_squad_digital.md). Um
item nasce como "pending" a partir da triagem (ou é adicionado manualmente
pelo advogado) e migra para "received" ou "waived" por revisão humana.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import DocumentChecklistStatus

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class CaseDocument(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Item do checklist de documentos exigido/entregue em um caso.

    origin identifica de onde veio a exigência do documento (ex.: "intake",
    "evidence", "human_review" — texto livre em vez de enum fechado, porque
    novos módulos podem apontar pendências no futuro sem exigir migration).
    """

    __tablename__ = "case_documents"
    __table_args__ = (UniqueConstraint("case_id", "name", name="uq_case_documents_case_id_name"),)

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DocumentChecklistStatus] = mapped_column(
        db_enum(DocumentChecklistStatus, "document_checklist_status"),
        nullable=False,
        default=DocumentChecklistStatus.PENDING,
    )
    origin: Mapped[str] = mapped_column(String(50), nullable=False, default="intake")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship()
    case: Mapped["Case"] = relationship(back_populates="documents")
