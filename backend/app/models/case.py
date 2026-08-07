"""Modelo do caso jurídico — unidade central de trabalho do Squad Digital."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import CaseArea, CaseStatus, FraudType, ModuleName, UrgencyLevel

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.case_document import CaseDocument
    from app.models.case_intake import CaseIntake
    from app.models.catalog import FraudModality, Platform
    from app.models.client import Client
    from app.models.evidence_file import EvidenceFile
    from app.models.tenant import Tenant
    from app.models.user import User


class Case(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Caso de Direito Digital aberto por um advogado para um tenant.

    Classificação — desde a Fase 2.7, plataforma e modalidade vêm dos catálogos
    por tenant (`platform_id`, `fraud_modality_id`; ver app/models/catalog.py).
    As colunas `platform` (texto) e `fraud_type` (enum) **permanecem como
    rótulo e família denormalizados** da entrada escolhida: é o que mantém o
    grafo LangGraph, os prompts e as migrations de seed lendo os mesmos campos
    de sempre enquanto o vocabulário do usuário se abre por baixo. Nunca
    escreva nessas duas colunas direto — derive-as da entrada de catálogo.

    area/matter e client_id são opcionais na criação: um caso pode ser aberto
    antes da triagem (módulo intake) classificar a área do Direito e associar
    o cliente relatado — ver prompts/digital/intake/triage.md.
    """

    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_cases_tenant_id_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: Identificador legível do caso dentro do escritório (ex.: "CAS-2026-000123"),
    #: emitido por app/core/identifiers.py. É o rótulo do caso na interface e nos
    #: prompts — o UUID fica na URL e nunca é exibido.
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platforms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fraud_modality_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fraud_modalities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    area: Mapped[CaseArea | None] = mapped_column(
        db_enum(CaseArea, "case_area"),
        nullable=True,
    )
    matter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Rótulo denormalizado de `platform_entry` — derivado, nunca escrito direto.
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Família denormalizada de `fraud_modality` — derivada, nunca escrita direto.
    fraud_type: Mapped[FraudType] = mapped_column(
        db_enum(FraudType, "fraud_type"),
        nullable=False,
    )
    urgency: Mapped[UrgencyLevel] = mapped_column(
        db_enum(UrgencyLevel, "urgency_level"),
        nullable=False,
        default=UrgencyLevel.MEDIUM,
    )
    status: Mapped[CaseStatus] = mapped_column(
        db_enum(CaseStatus, "case_status"),
        nullable=False,
        default=CaseStatus.DRAFT,
    )
    current_module: Mapped[ModuleName] = mapped_column(
        db_enum(ModuleName, "module_name"),
        nullable=False,
        default=ModuleName.INTAKE,
    )
    human_review_required: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="cases")
    user: Mapped["User"] = relationship(back_populates="cases")
    client: Mapped["Client | None"] = relationship(back_populates="cases")
    # platform_entry, e não "platform": o nome do atributo do relacionamento
    # não pode colidir com a coluna homônima que guarda o rótulo denormalizado.
    platform_entry: Mapped["Platform"] = relationship(back_populates="cases")
    fraud_modality: Mapped["FraudModality"] = relationship(back_populates="cases")
    intake: Mapped["CaseIntake | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    documents: Mapped[list["CaseDocument"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    evidence_files: Mapped[list["EvidenceFile"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
