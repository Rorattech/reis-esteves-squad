"""Modelo do cliente (parte lesada) — pessoa que relata o caso ao escritório."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, db_enum
from app.models.enums import MaritalStatus, PersonType

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.tenant import Tenant


class Client(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Cliente (pessoa física ou jurídica) de um tenant, potencial parte de um caso.

    Os campos de qualificação (documento, estado civil, profissão, endereço)
    existem porque são exatamente o que o CPC art. 319, II exige na petição
    inicial, e porque o endereço define o foro do consumidor (CDC art. 101, I)
    — que prompts/digital/evidence/specialist.md pede no output.

    document_number (CPF/CNPJ) é opcional: no primeiro contato o dado pode
    ainda não ter sido coletado — a unicidade só é verificada quando presente
    (múltiplos NULLs não colidem em UniqueConstraint no Postgres). Quando
    presente, é armazenado **apenas com dígitos** (ver app/core/documents.py):
    normalizar na escrita é o que faz a checagem de duplicidade funcionar
    independentemente de o advogado ter digitado com ou sem máscara.

    Segurança — CPF/CNPJ é chave de vinculação interna, **nunca credencial de
    acesso**. CPF no Brasil é dado amplamente vazado, então qualquer fluxo
    futuro que libere o dossiê do caso a quem "informar o CPF" seria um
    incidente de LGPD, não uma funcionalidade: a autenticação de um portal do
    cliente precisa de posse verificada (OTP no telefone/e-mail cadastrado) ou
    de token por caso emitido pelo advogado. Vale notar também que, mesmo
    quando o processo judicial é público (CPC art. 189), o dossiê dentro deste
    sistema — evidências, estratégia, minuta — é coberto por sigilo
    profissional (EOAB art. 34, VII) e não é público em nenhuma hipótese.
    """

    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_number", name="uq_clients_tenant_id_document_number"
        ),
        UniqueConstraint("tenant_id", "code", name="uq_clients_tenant_id_code"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Identificador legível do cliente dentro do escritório (ex.: "CLI-000042"),
    #: emitido por app/core/identifiers.py. É o que aparece na interface — o
    #: UUID é chave primária e nunca é exibido ao advogado.
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    person_type: Mapped[PersonType] = mapped_column(
        db_enum(PersonType, "person_type"),
        nullable=False,
        default=PersonType.INDIVIDUAL,
    )
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Qualificação (CPC art. 319, II) — só se aplica a pessoa física ---
    rg: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rg_issuer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(60), nullable=True)
    marital_status: Mapped[MaritalStatus | None] = mapped_column(
        db_enum(MaritalStatus, "marital_status"),
        nullable=True,
    )
    profession: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- Endereço — define o foro do consumidor (CDC art. 101, I) ---
    address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_complement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: CEP apenas com dígitos, como o documento (ver app/core/documents.py).
    address_zip_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="clients")
    cases: Mapped[list["Case"]] = relationship(back_populates="client")
