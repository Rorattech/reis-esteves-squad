"""Modelo do escritório de advocacia (tenant) — raiz do isolamento multitenant."""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.case import Case
    from app.models.client import Client
    from app.models.user import User


class Tenant(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Escritório de advocacia cliente da plataforma.

    É a raiz do isolamento multitenant: seu próprio `id` é o valor usado como
    tenant_id nas demais tabelas e na política de RLS (ver docs/architecture.md, seção 4).
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    clients: Mapped[list["Client"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    cases: Mapped[list["Case"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
