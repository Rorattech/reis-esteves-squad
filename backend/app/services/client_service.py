"""Serviço de cadastro de clientes (partes lesadas) — Fase 2, Intake.

Toda função aqui recebe tenant_id explícito (nunca inferido do payload) e
grava uma entrada em audit_logs antes de retornar (CLAUDE.md, seções 7 e 10).
Não há chamada a modelo de IA nesta camada — model_used="n/a" é o valor
convencionado no projeto para ações puramente humanas (ver backend/tests/test_audit.py).

Nenhuma função faz commit: a transação pertence a quem chamou. É isso que
permite cadastrar o cliente e abrir o caso atomicamente (ver
app/api/v1/cases.py) — um caso que falha na criação não deixa cliente órfão.

Privacidade: a auditoria guarda apenas o SHA-256 do payload
(create_audit_entry -> _stable_hash), então CPF, RG e endereço nunca são
persistidos em claro em audit_logs. O `metadata` da entrada também não pode
carregar PII — só identificadores.
"""

import time
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.documents import is_valid_cnpj, is_valid_cpf
from app.core.identifiers import CodeScope, next_code
from app.models.client import Client
from app.models.enums import PersonType
from app.models.schemas.client import ClientCreate, ClientUpdate

_MODEL_USED_MANUAL = "n/a"

#: Teto de resultados de uma busca de clientes, para não devolver a base
#: inteira em um combobox.
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100


class DuplicateClientDocumentError(Exception):
    """Já existe um cliente com este CPF/CNPJ neste escritório."""


class DocumentPersonTypeMismatchError(Exception):
    """O documento não corresponde à natureza (PF/PJ) informada para o cliente."""


def _assert_document_matches_person_type(
    document_number: str | None, person_type: PersonType
) -> None:
    """Confere o documento contra a natureza jurídica efetiva do cliente.

    O schema valida o par que veio no payload; esta checagem existe para o
    PATCH, em que a natureza pode estar só no registro e o documento só no
    payload (ou vice-versa) — sem ela, trocar person_type para "company"
    deixaria um CPF gravado como se fosse CNPJ.

    Args:
        document_number: Documento já normalizado (só dígitos), ou None.
        person_type: Natureza que o cliente terá ao final da operação.

    Raises:
        DocumentPersonTypeMismatchError: Se o documento não bater com a natureza.
    """
    if document_number is None:
        return
    valid = (
        is_valid_cpf(document_number)
        if person_type is PersonType.INDIVIDUAL
        else is_valid_cnpj(document_number)
    )
    if not valid:
        raise DocumentPersonTypeMismatchError(person_type.value)


async def _assert_document_is_unique(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_number: str | None,
    exclude_client_id: uuid.UUID | None = None,
) -> None:
    """Rejeita documento já cadastrado no escritório antes de o banco rejeitar.

    A UniqueConstraint uq_clients_tenant_id_document_number é a garantia real;
    esta checagem só existe para a API poder responder 409 com uma mensagem
    útil em vez de deixar o IntegrityError virar 500.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        document_number: Documento já normalizado, ou None.
        exclude_client_id: Cliente sendo atualizado, que não conta como conflito.

    Raises:
        DuplicateClientDocumentError: Se outro cliente do tenant já usa o documento.
    """
    if document_number is None:
        return
    query = select(Client.id).where(
        Client.tenant_id == tenant_id,
        Client.document_number == document_number,
    )
    if exclude_client_id is not None:
        query = query.where(Client.id != exclude_client_id)
    if await session.scalar(query) is not None:
        raise DuplicateClientDocumentError(document_number)


async def create_client(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: ClientCreate,
) -> Client:
    """Cadastra um novo cliente para o tenant autenticado.

    Não faz commit — participa da transação de quem chamou.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        payload: Dados do cliente, já validados e normalizados pelo schema.

    Returns:
        Cliente recém-criado, com `code` emitido.

    Raises:
        DuplicateClientDocumentError: Se o documento já existir neste tenant.
        DocumentPersonTypeMismatchError: Se o documento não bater com a natureza.
    """
    started_at = time.monotonic()
    _assert_document_matches_person_type(payload.document_number, payload.person_type)
    await _assert_document_is_unique(
        session, tenant_id=tenant_id, document_number=payload.document_number
    )

    client = Client(
        tenant_id=tenant_id,
        code=await next_code(session, tenant_id=tenant_id, scope=CodeScope.CLIENT),
        **payload.model_dump(),
    )
    session.add(client)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="cadastrou cliente",
        module="intake",
        input_data=payload.model_dump(mode="json"),
        output_data={"client_id": str(client.id), "code": client.code},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        # Sem PII: só identificadores (ver docstring do módulo).
        metadata={"entity": "client", "client_id": str(client.id), "code": client.code},
    )
    # case_id=None: o cliente ainda não pertence a nenhum caso no momento do
    # cadastro (audit_logs.case_id é opcional — ver app/models/audit_log.py).
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))
    return client


async def get_client(
    session: AsyncSession, *, tenant_id: uuid.UUID, client_id: uuid.UUID
) -> Client | None:
    """Busca um cliente do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        client_id: ID do cliente.

    Returns:
        O cliente, ou None se não existir neste tenant.
    """
    return await session.scalar(
        select(Client).where(Client.tenant_id == tenant_id, Client.id == client_id)
    )


async def search_clients(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    search: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[Client]:
    """Busca clientes do escritório por nome, documento ou código.

    A busca por documento ignora a máscara: o advogado digita "529.982.247-25"
    e encontra o cliente gravado como "52998224725" (ver app/core/documents.py).

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        search: Termo livre — nome parcial, documento (com ou sem máscara) ou
            código do cliente. None lista os mais recentes.
        limit: Teto de resultados, limitado a MAX_SEARCH_LIMIT.

    Returns:
        Clientes do tenant que casam com o termo, por nome.
    """
    query = select(Client).where(Client.tenant_id == tenant_id)

    if search and search.strip():
        term = search.strip()
        conditions = [
            Client.full_name.ilike(f"%{term}%"),
            Client.code.ilike(f"%{term}%"),
        ]
        digits = "".join(character for character in term if character.isdigit())
        if digits:
            conditions.append(Client.document_number.ilike(f"%{digits}%"))
        query = query.where(or_(*conditions))

    result = await session.scalars(
        query.order_by(func.lower(Client.full_name)).limit(min(limit, MAX_SEARCH_LIMIT))
    )
    return list(result.all())


async def update_client(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    client_id: uuid.UUID,
    payload: ClientUpdate,
) -> Client | None:
    """Atualiza campos de um cliente existente do tenant autenticado.

    Não faz commit — participa da transação de quem chamou.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        actor_id: ID do usuário autenticado que está realizando a ação.
        client_id: ID do cliente a atualizar.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).

    Returns:
        Cliente atualizado, ou None se não existir neste tenant.

    Raises:
        DuplicateClientDocumentError: Se o documento já pertencer a outro cliente.
        DocumentPersonTypeMismatchError: Se o documento não bater com a natureza.
    """
    started_at = time.monotonic()
    client = await get_client(session, tenant_id=tenant_id, client_id=client_id)
    if client is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    # Natureza e documento são validados juntos contra o estado FINAL do
    # registro, não só contra o que veio no payload.
    person_type = updates.get("person_type", client.person_type)
    document_number = updates.get("document_number", client.document_number)
    _assert_document_matches_person_type(document_number, person_type)
    await _assert_document_is_unique(
        session,
        tenant_id=tenant_id,
        document_number=document_number,
        exclude_client_id=client_id,
    )

    for field, value in updates.items():
        setattr(client, field, value)
    await session.flush()

    entry = create_audit_entry(
        actor_id=str(actor_id),
        action="atualizou cliente",
        module="intake",
        input_data=payload.model_dump(exclude_unset=True, mode="json"),
        output_data={"client_id": str(client.id), "code": client.code},
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={
            "entity": "client",
            "client_id": str(client.id),
            "code": client.code,
            # Nomes dos campos alterados — não os valores (PII).
            "changed_fields": sorted(updates),
        },
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=None))
    return client
