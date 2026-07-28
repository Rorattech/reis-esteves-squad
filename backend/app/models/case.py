"""Modelo do caso jurídico — unidade central de trabalho do Squad Digital."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import CaseStatus, FraudType, UrgencyLevel

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.tenant import Tenant
    from app.models.user import User


class Case(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Caso de Direito Digital aberto por um advogado para um tenant.

    platform é texto livre (Meta, Shopee, Mercado Livre, WhatsApp, etc. — lista
    aberta, ver docs/architecture.md, módulo 1) em vez de enum fechado.
    """

    __tablename__ = "cases"

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
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="cases")
    user: Mapped["User"] = relationship(back_populates="cases")
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
