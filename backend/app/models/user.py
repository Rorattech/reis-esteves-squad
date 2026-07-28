"""Modelo de usuário (advogado, paralegal, admin ou viewer) de um tenant."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class User(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Usuário autenticado, sempre associado a um único tenant."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        db_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.LAWYER,
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    cases: Mapped[list["Case"]] = relationship(back_populates="user")
