"""Achados probatórios persistidos do módulo Evidence (Fase 3.3).

Espelho consultável de `orchestrator.state.EvidenceFinding` para a interface
(Fases 3.4/3.5 — inventário probatório e pendências): cada linha é um achado
dos agentes documental/specialist, rastreável à evidência de origem quando
category != "missing_info".

A cada execução do módulo Evidence os achados ainda pendentes de revisão são
substituídos pelos novos (uma re-execução é uma nova recomendação, não uma
continuação); o histórico completo permanece em audit_logs e nos checkpoints
do CaseState.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class EvidenceFindingRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Um achado probatório persistido, sempre DRAFT_PENDING_REVIEW ao nascer.

    `status` segue DraftStatus (orchestrator/state.py): nenhum achado vira
    "APPROVED" sem registro de aprovação humana com actor e timestamp em
    audit_logs (CLAUDE.md, seção 2).
    """

    __tablename__ = "evidence_findings"

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
    # Nulo apenas para lacunas (category == "missing_info") — fatos e
    # inferências sempre apontam a evidência de origem (roadmap 3.3).
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str] = mapped_column(String(10), nullable=False)
    suggested_use: Mapped[str] = mapped_column(Text, nullable=False)
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT_PENDING_REVIEW"
    )
