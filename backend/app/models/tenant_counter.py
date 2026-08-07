"""Contadores sequenciais por escritório — origem dos códigos legíveis de caso e cliente."""

import uuid

from sqlalchemy import ForeignKey, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantCounter(Base):
    """Último número emitido por escritório, para um escopo e ano.

    Uma SEQUENCE do Postgres é global ao banco: usá-la faria o primeiro caso do
    segundo escritório nascer como CAS-2026-000008 só porque o primeiro
    escritório já abriu sete. Cada tenant precisa da própria contagem começando
    em 1, e é isso que esta tabela guarda.

    A alocação acontece em uma única instrução com ON CONFLICT DO UPDATE
    (ver app/core/identifiers.py) — o UPDATE toma o row lock, então duas
    requests simultâneas do mesmo tenant serializam naturalmente e nunca
    recebem o mesmo número.

    Buracos na sequência são esperados e aceitáveis: um caso que falha depois de
    alocar o código deixa aquele número sem dono. O código é identificador
    legível, não contagem contábil de casos.
    """

    __tablename__ = "tenant_counters"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "scope", "year", name="pk_tenant_counters"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Que série este contador numera — "case" ou "client" (ver CodeScope).
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Ano da série. 0 para escopos perenes, que não reiniciam a cada ano.
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
