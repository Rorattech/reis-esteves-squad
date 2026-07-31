"""Engine e sessões assíncronas do PostgreSQL (SQLAlchemy 2.0 async).

O pool de conexões reutiliza conexões físicas entre requests diferentes, e
`SELECT set_config(..., false)` (não-LOCAL) sobrevive a um simples ROLLBACK de
retorno ao pool. Por isso toda função aqui que abre uma sessão nova define
explicitamente app.current_tenant e app.bootstrap logo na primeira instrução
— nunca assume que a conexão está "limpa" — para que um valor de uma request
anterior nunca vaze para a próxima que reutilizar a mesma conexão física.

app.current_tenant é resetado para '' (string vazia), não NULL: GUCs
customizados (placeholder) do Postgres não voltam a NULL via RESET ou
set_config(..., NULL, ...) depois de setados numa sessão — a policy
tenant_isolation trata ambos os casos (NULL e '') como "nenhum tenant" via
NULLIF antes do cast ::uuid (ver migration 3abdfd696724).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

_RESET_SESSION_GUCS = text(
    "SELECT set_config('app.current_tenant', '', false), "
    "set_config('app.bootstrap', 'false', false)"
)
_SET_BOOTSTRAP_GUC = text(
    "SELECT set_config('app.current_tenant', '', false), "
    "set_config('app.bootstrap', 'true', false)"
)


_SET_TENANT_GUC = text(
    "SELECT set_config('app.current_tenant', :tenant_id, false), "
    "set_config('app.bootstrap', 'false', false)"
)


@asynccontextmanager
async def tenant_scoped_session(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Abre uma sessão escopada a um tenant fora do ciclo de uma request HTTP.

    Uso restrito a tarefas de background (ex.: pipeline de extração de
    evidências — Fase 3.2), onde a sessão do TenantMiddleware já foi fechada.
    O tenant_id DEVE vir de um contexto autenticado anterior — nunca de input
    do usuário (CLAUDE.md, seção 7).

    Args:
        tenant_id: Tenant dono dos dados que a tarefa vai ler/escrever.

    Yields:
        Sessão SQLAlchemy assíncrona com `app.current_tenant` configurado.
    """
    async with async_session_factory() as session:
        await session.execute(_SET_TENANT_GUC, {"tenant_id": str(tenant_id)})
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    """Abre uma sessão assíncrona sem escopo de tenant e sem bypass de RLS.

    Uso restrito a rotas públicas que não leem/escrevem dados de tenant (ex.:
    health checks). Rotas de bootstrap de autenticação (registro, login,
    refresh) devem usar `get_auth_bootstrap_session`; todas as demais rotas
    protegidas devem usar `get_tenant_session`.

    Returns:
        Sessão SQLAlchemy assíncrona, fechada automaticamente ao final da request.
    """
    async with async_session_factory() as session:
        await session.execute(_RESET_SESSION_GUCS)
        yield session


async def get_auth_bootstrap_session() -> AsyncIterator[AsyncSession]:
    """Abre uma sessão com bypass de RLS restrito às tabelas tenants e users.

    Uso exclusivo das rotas de registro, login e refresh (app/api/v1/auth.py):
    são as únicas operações que legitimamente precisam criar o primeiro tenant
    ou localizar um usuário sem um tenant_id autenticado ainda. O bypass é
    concedido pela policy `auth_bootstrap` (ver migration de RLS) apenas nas
    tabelas tenants/users — cases e audit_logs permanecem bloqueadas mesmo que
    app.bootstrap fique 'true' por engano nesta sessão.

    Returns:
        Sessão SQLAlchemy assíncrona com app.bootstrap='true' nesta conexão.
    """
    async with async_session_factory() as session:
        await session.execute(_SET_BOOTSTRAP_GUC)
        yield session


async def get_tenant_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Retorna a sessão já escopada por tenant, injetada pelo TenantMiddleware.

    Args:
        request: Request HTTP corrente, com `state.db` definido pelo middleware.

    Returns:
        Sessão SQLAlchemy assíncrona com `app.current_tenant` configurado (ver
        CLAUDE.md, seção 7, e app/middleware/tenant.py).

    Raises:
        RuntimeError: Se o TenantMiddleware não injetou a sessão na request —
            indica rota protegida registrada fora do escopo do middleware.
    """
    session = getattr(request.state, "db", None)
    if session is None:
        raise RuntimeError(
            "Sessão escopada por tenant ausente — verifique se TenantMiddleware "
            "está registrado e se a rota não está na lista de caminhos públicos."
        )
    yield session
