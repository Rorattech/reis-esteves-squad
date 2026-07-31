"""Modelo do arquivo de evidência digital de um caso (Fase 3 — módulo evidence).

Distinto de CaseDocument (app/models/case_document.py), que é só o item do
checklist (nome/status/origem). EvidenceFile é o arquivo em si: original
preservado sem alteração, com hash de integridade, storage_key privado e
status de processamento (ver docs/roadmap_mvp_squad_digital.md, 3.1).

A cadeia de custódia simplificada (quem enviou, quando, de onde, quais
processamentos) não tem tabela própria: é derivada de audit_logs filtrando
por metadata_.entity == "evidence" e metadata_.evidence_id (mesmo padrão de
app/services/case_document_service.py) — evita duplicar o que audit_logs já
garante com tenant_id e RLS.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import EvidenceProcessingStatus

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.evidence_extraction import EvidenceExtraction
    from app.models.tenant import Tenant
    from app.models.user import User


class EvidenceFile(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Arquivo de evidência digital vinculado a um caso e tenant.

    extension é derivada do mime_type validado no upload (nunca do nome de
    arquivo informado pelo cliente) — usada para montar storage_key, que por
    sua vez nunca é exposto como URL pública (ver app/core/storage.py).

    duplicate_of_id aponta para a primeira EvidenceFile com o mesmo
    sha256_hash já vista neste tenant (dedup por tenant, não por caso — ver
    roadmap 3.1: "duplicidade por hash dentro do mesmo tenant"). O arquivo
    ainda assim é armazenado de forma independente: cada upload é um evento
    de custódia distinto, mesmo quando o conteúdo é idêntico.
    """

    __tablename__ = "evidence_files"
    __table_args__ = (UniqueConstraint("storage_key", name="uq_evidence_files_storage_key"),)

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
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    origin: Mapped[str] = mapped_column(String(50), nullable=False, default="upload_portal")
    status: Mapped[EvidenceProcessingStatus] = mapped_column(
        db_enum(EvidenceProcessingStatus, "evidence_processing_status"),
        nullable=False,
        default=EvidenceProcessingStatus.RECEIVED,
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship()
    case: Mapped["Case"] = relationship(back_populates="evidence_files")
    uploaded_by_user: Mapped["User"] = relationship(foreign_keys=[uploaded_by])
    duplicate_of: Mapped["EvidenceFile | None"] = relationship(
        remote_side="EvidenceFile.id", foreign_keys=[duplicate_of_id]
    )
    extractions: Mapped[list["EvidenceExtraction"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )
