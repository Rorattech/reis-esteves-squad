"""Base declarativa e mixins compartilhados pelos modelos SQLAlchemy."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos ORM da aplicação."""


class UUIDPrimaryKeyMixin:
    """Adiciona uma chave primária UUID gerada pelo Postgres (gen_random_uuid())."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAtMixin:
    """Adiciona a coluna created_at, preenchida pelo servidor no momento do insert."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def db_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Cria um ENUM nativo do Postgres usando os .value dos membros (ex: "lawyer"),
    em vez do padrão do SQLAlchemy de usar o nome do membro (ex: "LAWYER").
    """
    return Enum(
        enum_cls, name=name, native_enum=True, values_callable=lambda obj: [e.value for e in obj]
    )
