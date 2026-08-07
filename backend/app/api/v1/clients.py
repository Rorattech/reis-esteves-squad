"""Rotas de cadastro de clientes (CLAUDE.md, seção 7 — multitenancy obrigatória).

Todas as rotas exigem TenantMiddleware (JWT válido) e usam a sessão já escopada
por tenant injetada em request.state.db — nunca aceitam tenant_id vindo do
payload. O commit fica aqui, na borda da request: o serviço só faz flush, para
que criar cliente e abrir caso possam compartilhar uma transação (ver
app/api/v1/cases.py).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.core.rbac import require_role
from app.models.client import Client
from app.models.enums import UserRole
from app.models.schemas.client import (
    ClientCreate,
    ClientResponse,
    ClientSearchRequest,
    ClientUpdate,
)
from app.services.client_service import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    DocumentPersonTypeMismatchError,
    DuplicateClientDocumentError,
    create_client,
    get_client,
    search_clients,
    update_client,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/clients", tags=["clients"])

# viewer só lê; cadastrar/editar cliente exige papel operacional (CLAUDE.md, seção 12).
_require_client_writer = require_role(UserRole.ADMIN, UserRole.LAWYER, UserRole.PARALEGAL)

_DUPLICATE_DETAIL = "Já existe um cliente com este CPF/CNPJ neste escritório."
_MISMATCH_DETAIL = (
    "Documento incompatível com a natureza do cliente — pessoa física usa CPF "
    "e pessoa jurídica usa CNPJ."
)


@router.post(
    "",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_client_writer)],
)
async def create_client_route(
    payload: ClientCreate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Client:
    """Cadastra um cliente para o escritório autenticado.

    Args:
        payload: Qualificação do cliente — nome, natureza, documento, contato
            e endereço.
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`
            definidos pelo TenantMiddleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Cliente recém-criado, com o código legível emitido.

    Raises:
        HTTPException: 409 se o documento já existir neste escritório; 422 se o
            documento não corresponder à natureza informada.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        client = await create_client(
            session,
            tenant_id=tenant_id,
            actor_id=uuid.UUID(request.state.user_id),
            payload=payload,
        )
    except DuplicateClientDocumentError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from error
    except DocumentPersonTypeMismatchError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_MISMATCH_DETAIL
        ) from error

    await session.commit()
    await session.refresh(client)

    logger.info("clients.create", client_code=client.code, tenant_id=request.state.tenant_id)
    return client


@router.post("/search", response_model=list[ClientResponse])
async def search_clients_route(
    payload: ClientSearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Client]:
    """Busca clientes do escritório autenticado.

    É POST apesar de ser uma leitura: o termo pode ser um nome ou um CPF, e
    query string vaza para access log, histórico do navegador, cabeçalho
    Referer e cache de proxy (CLAUDE.md, seção 12). O corpo não.

    Args:
        payload: Termo de busca e teto de resultados.
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Clientes que casam com o termo, ordenados por nome.
    """
    return await search_clients(
        session,
        tenant_id=uuid.UUID(request.state.tenant_id),
        search=payload.search,
        limit=payload.limit,
    )


@router.get("", response_model=list[ClientResponse])
async def list_clients_route(
    request: Request,
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Client]:
    """Lista os clientes do escritório autenticado, por nome.

    Sem parâmetro de busca de propósito — buscar é `POST /clients/search`,
    para que nenhum dado pessoal apareça na URL.

    Args:
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        limit: Teto de resultados.
        session: Sessão do banco já escopada por tenant.

    Returns:
        Clientes do escritório, ordenados por nome.
    """
    return await search_clients(session, tenant_id=uuid.UUID(request.state.tenant_id), limit=limit)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client_route(
    client_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Client:
    """Retorna a ficha completa de um cliente do escritório autenticado.

    Args:
        client_id: ID do cliente.
        request: Request HTTP corrente, com `state.tenant_id` definido pelo middleware.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O cliente solicitado.

    Raises:
        HTTPException: 404 se o cliente não existir neste escritório.
    """
    client = await get_client(
        session, tenant_id=uuid.UUID(request.state.tenant_id), client_id=client_id
    )
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")
    return client


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(_require_client_writer)],
)
async def update_client_route(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
) -> Client:
    """Atualiza a qualificação de um cliente do escritório autenticado.

    Args:
        client_id: ID do cliente.
        payload: Campos a atualizar — todos opcionais (semântica PATCH).
        request: Request HTTP corrente, com `state.tenant_id`/`state.user_id`.
        session: Sessão do banco já escopada por tenant.

    Returns:
        O cliente atualizado.

    Raises:
        HTTPException: 404 se o cliente não existir; 409 se o documento já
            pertencer a outro cliente; 422 se o documento não corresponder à
            natureza resultante.
    """
    tenant_id = uuid.UUID(request.state.tenant_id)
    try:
        client = await update_client(
            session,
            tenant_id=tenant_id,
            actor_id=uuid.UUID(request.state.user_id),
            client_id=client_id,
            payload=payload,
        )
    except DuplicateClientDocumentError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from error
    except DocumentPersonTypeMismatchError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_MISMATCH_DETAIL
        ) from error

    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    await session.commit()
    await session.refresh(client)

    logger.info("clients.update", client_code=client.code, tenant_id=request.state.tenant_id)
    return client
