"""Schemas Pydantic do cliente (ClientCreate, ClientUpdate, ClientResponse).

tenant_id nunca aparece em ClientCreate/ClientUpdate: é extraído do JWT pelo
TenantMiddleware, igual ao padrão de schemas/case.py (CLAUDE.md, seção 7).

O documento é validado (dígito verificador) e normalizado para só dígitos já
no schema, antes de chegar ao serviço: é o que faz a checagem de duplicidade
por CPF funcionar independentemente da máscara digitada, e o que impede um
"CPF" impossível de virar qualificação de uma petição.
"""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.documents import (
    is_valid_cnpj,
    is_valid_cpf,
    normalize_zip_code,
    strip_non_digits,
)
from app.models.enums import MaritalStatus, PersonType

#: Unidades federativas aceitas em address_state.
_BRAZILIAN_STATES = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


class ClientBase(BaseModel):
    """Campos de qualificação compartilhados entre criação e atualização."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    person_type: PersonType | None = None
    document_number: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)

    rg: str | None = Field(default=None, max_length=32)
    rg_issuer: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    nationality: str | None = Field(default=None, max_length=60)
    marital_status: MaritalStatus | None = None
    profession: str | None = Field(default=None, max_length=120)

    address_street: str | None = Field(default=None, max_length=255)
    address_number: str | None = Field(default=None, max_length=20)
    address_complement: str | None = Field(default=None, max_length=120)
    address_district: str | None = Field(default=None, max_length=120)
    address_city: str | None = Field(default=None, max_length=120)
    address_state: str | None = Field(default=None, max_length=2)
    address_zip_code: str | None = Field(default=None, max_length=16)

    @field_validator("document_number", "address_zip_code", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Trata string vazia como ausência de dado.

        Um campo opcional deixado em branco no formulário chega como "" — sem
        isso, "" viraria um documento vazio que colide com o UNIQUE por tenant
        no segundo cliente sem documento.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("address_state")
    @classmethod
    def _validate_state(cls, value: str | None) -> str | None:
        """Aceita apenas siglas de UF válidas, sempre em maiúsculas."""
        if value is None:
            return None
        uf = value.strip().upper()
        if uf not in _BRAZILIAN_STATES:
            raise ValueError("UF inválida — use a sigla de duas letras (ex.: SP).")
        return uf

    @field_validator("address_zip_code")
    @classmethod
    def _validate_zip_code(cls, value: str | None) -> str | None:
        """Normaliza o CEP para 8 dígitos, rejeitando o que não for CEP."""
        if value is None:
            return None
        normalized = normalize_zip_code(value)
        if normalized is None:
            raise ValueError("CEP inválido — informe 8 dígitos (ex.: 01310-100).")
        return normalized

    @model_validator(mode="after")
    def _validate_document(self) -> Self:
        """Valida o documento contra a natureza do cliente e o normaliza.

        A natureza determina qual validação se aplica: pessoa física tem CPF,
        jurídica tem CNPJ. Quando `person_type` não vem no payload (semântica
        PATCH, em que o valor persistido pode ser outro), aceita-se qualquer um
        dos dois formatos válidos — o serviço é quem confronta com o registro.
        """
        if self.document_number is None:
            return self

        digits = strip_non_digits(self.document_number)
        if self.person_type is PersonType.INDIVIDUAL:
            valid = is_valid_cpf(digits)
            message = "CPF inválido — confira os dígitos."
        elif self.person_type is PersonType.COMPANY:
            valid = is_valid_cnpj(digits)
            message = "CNPJ inválido — confira os dígitos."
        else:
            valid = is_valid_cpf(digits) or is_valid_cnpj(digits)
            message = "Documento inválido — informe um CPF ou CNPJ válido."

        if not valid:
            raise ValueError(message)

        # Só dígitos no banco: ver docstring do módulo.
        self.document_number = digits
        return self


class ClientCreate(ClientBase):
    """Dados para o cadastro de um cliente (parte lesada) pelo tenant autenticado."""

    full_name: str = Field(min_length=1, max_length=255)
    person_type: PersonType = PersonType.INDIVIDUAL


class ClientUpdate(ClientBase):
    """Campos atualizáveis de um cliente existente — todos opcionais (semântica PATCH)."""


class ClientSearchRequest(BaseModel):
    """Termo de busca de clientes, enviado no corpo — nunca na URL.

    Nome e CPF são dados pessoais, e query string vaza para access log do
    servidor, histórico do navegador, cabeçalho Referer e cache de proxy
    (CLAUDE.md, seção 12 — nunca logar CPF nem dados pessoais de clientes).
    Por isso a busca é POST apesar de ser uma leitura.
    """

    search: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=20, ge=1, le=100)


class ClientSummary(BaseModel):
    """Cliente reduzido ao que identifica o caso numa lista.

    Sem documento de propósito: a lista de casos não precisa de CPF para o
    advogado reconhecer o caso, e todo campo de PII a menos numa resposta de
    listagem é uma superfície de vazamento a menos (CLAUDE.md, seção 12).
    O dado completo está em GET /api/v1/clients/{id}.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    code: str
    full_name: str


class ClientResponse(BaseModel):
    """Representação pública completa de um cliente, retornada pela API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    full_name: str
    person_type: PersonType
    document_number: str | None
    email: str | None
    phone: str | None

    rg: str | None
    rg_issuer: str | None
    birth_date: date | None
    nationality: str | None
    marital_status: MaritalStatus | None
    profession: str | None

    address_street: str | None
    address_number: str | None
    address_complement: str | None
    address_district: str | None
    address_city: str | None
    address_state: str | None
    address_zip_code: str | None

    created_at: datetime
    updated_at: datetime
