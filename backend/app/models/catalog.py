"""Catálogos de classificação do caso — plataformas e modalidades de golpe.

Antes da Fase 2.7 a plataforma era texto livre em `cases.platform` (então
"WhatsApp", "whatsapp" e "Whats" viravam três plataformas distintas) e a
modalidade era um enum fechado de cinco valores (então o escritório não
conseguia cadastrar um golpe novo sem deploy) — exatamente o inverso do que o
produto precisa. As duas passam a ser catálogos por tenant: vocabulário
controlado no momento de escolher, mas extensível pelo próprio escritório.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import FraudType

if TYPE_CHECKING:
    from app.models.case import Case


class _CatalogEntryMixin(UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Colunas comuns às duas tabelas de catálogo."""

    #: Identificador estável da entrada dentro do tenant (ex.: "mercado_livre").
    #: É por ele que a migration de backfill e o seed reconhecem uma entrada
    #: padrão — o label pode ser renomeado pelo escritório, o slug não.
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Texto exibido ao advogado e gravado como rótulo denormalizado no caso.
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    #: True para as entradas semeadas com o produto, False para as que o
    #: escritório cadastrou via "Outro". Entradas de sistema não são excluídas,
    #: apenas desativadas — casos antigos continuam apontando para elas.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Entradas inativas somem dos selects mas continuam válidas nos casos que
    #: já as referenciam.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class Platform(_CatalogEntryMixin, Base):
    """Plataforma onde a fraude ocorreu (Meta, Mercado Livre, WhatsApp, PIX...)."""

    __tablename__ = "platforms"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_platforms_tenant_id_slug"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Usuário que cadastrou a entrada. NULL nas entradas de sistema, que vêm
    #: da migration/seed e não têm autor humano.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cases: Mapped[list["Case"]] = relationship(back_populates="platform_entry")


class FraudModality(_CatalogEntryMixin, Base):
    """Modalidade do golpe cadastrada pelo escritório, ligada a uma família do enum.

    `family` é o que permite o vocabulário ser aberto sem quebrar os agentes:
    o advogado cadastra "golpe da falsa central de atendimento" e declara que
    aquilo é da família `pix`; o grafo e os prompts continuam raciocinando
    sobre as cinco famílias de FraudType, que é o que eles conhecem.
    """

    __tablename__ = "fraud_modalities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_fraud_modalities_tenant_id_slug"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family: Mapped[FraudType] = mapped_column(
        db_enum(FraudType, "fraud_type"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cases: Mapped[list["Case"]] = relationship(back_populates="fraud_modality")
