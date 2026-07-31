"""Artefatos derivados de uma evidência (Fase 3.2 — texto extraído) e a
revisão humana desses artefatos (Fase 3.5).

O texto extraído mora aqui, em `evidence_extractions` — NUNCA no arquivo
original (roadmap 3.2: "Armazenar texto extraído e artefatos derivados sem
alterar o original"). Cada execução do pipeline é uma linha nova, imutável:
reprocessar cria outro registro, preservando o histórico completo de
ferramenta, versão, hashes e resultado.

A correção humana (`evidence_extraction_reviews`) também é só registro: um
veredito auditado sobre o derivado, jamais uma substituição do texto
(roadmap 3.5: "Uma correção humana deve criar registro/auditoria, não
substituir o original").
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import ExtractionOutcome, ExtractionReviewVerdict

if TYPE_CHECKING:
    from app.models.evidence_file import EvidenceFile
    from app.models.user import User


class EvidenceExtraction(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Uma execução do pipeline de extração sobre uma evidência.

    confidence vai de 0.0 a 1.0 e nunca é apresentada como certeza — OCR e
    transcrição são conteúdo derivado, sujeito a erro, e a interface deve
    dizer isso (roadmap 3.2: "Não afirmar que OCR é prova perfeita").
    """

    __tablename__ = "evidence_extractions"

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
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Método efetivamente usado: "plain_text" | "pdf_text" | "image_ocr" |
    # "pdf_ocr" — String, não enum de banco: novos extratores não devem exigir
    # migration.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[ExtractionOutcome] = mapped_column(
        db_enum(ExtractionOutcome, "extraction_outcome"), nullable=False
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Mensagem técnica segura — nunca conteúdo do documento (CLAUDE.md, seção 12).
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence: Mapped["EvidenceFile"] = relationship(back_populates="extractions")
    reviews: Mapped[list["EvidenceExtractionReview"]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan"
    )


class EvidenceExtractionReview(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Revisão humana de um texto extraído — confirma ou aponta erro, auditada."""

    __tablename__ = "evidence_extraction_reviews"

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
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    verdict: Mapped[ExtractionReviewVerdict] = mapped_column(
        db_enum(ExtractionReviewVerdict, "extraction_review_verdict"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction: Mapped["EvidenceExtraction"] = relationship(back_populates="reviews")
    reviewer: Mapped["User"] = relationship()
