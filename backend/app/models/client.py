"""Modelo do cliente (parte lesada) — pessoa que relata o caso ao escritório."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class Client(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Cliente (pessoa física ou jurídica) de um tenant, potencial parte de um caso.

    document_number (CPF/CNPJ) é opcional: no primeiro contato o dado pode
    ainda não ter sido coletado — a unicidade só é verificada quando presente
    (múltiplos NULLs não colidem em UniqueConstraint no Postgres).
    """

    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_number", name="uq_clients_tenant_id_document_number"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="clients")
    cases: Mapped[list["Case"]] = relationship(back_populates="client")
