"""Engine e sessões assíncronas do PostgreSQL (SQLAlchemy 2.0 async).

O escopo de RLS de uma sessão (app.current_tenant / app.bootstrap) é declarado
uma vez, em `session.info`, por `scope_session_to_tenant` /
`scope_session_to_auth_bootstrap`, e é **reaplicado no início de cada
transação** pelo listener `_apply_rls_scope` — nunca uma única vez na abertura
da sessão.

Isso não é preciosismo: o pool devolve a conexão física ao dar `commit()`, e a
instrução seguinte da MESMA sessão (ex.: o SELECT de `session.refresh()` logo
depois de inserir um `Case`) pode sair por OUTRA conexão, com o
app.current_tenant deixado por uma request anterior — inclusive o '' de
`get_auth_bootstrap_session` (login). A RLS então esconde a linha recém-criada
e o refresh estoura 500. Reaplicar por transação é o que garante que toda
instrução de uma sessão enxergue o tenant certo, em qualquer conexão.

As GUCs são setadas como LOCAL (`set_config(..., true)`): morrem junto com a
transação, então nenhum valor de tenant sobrevive no pool para vazar para a
request seguinte (CLAUDE.md, seção 7).

app.current_tenant é representado por '' (string vazia), não NULL, quando não
há tenant: GUCs customizados (placeholder) do Postgres não voltam a NULL via
RESET ou set_config(..., NULL, ...) depois de setados — a policy
tenant_isolation trata ambos os casos (NULL e '') como "nenhum tenant" via
NULLIF antes do cast ::uuid (ver migration 3abdfd696724).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

#: Chaves em `session.info` que guardam o escopo de RLS declarado para a sessão.
_TENANT_INFO_KEY = "app_current_tenant"
_BOOTSTRAP_INFO_KEY = "app_bootstrap"

# set_config com is_local=true: vale só até o fim da transação corrente. O
# parâmetro ligado (em vez de SET direto) protege contra injection.
_APPLY_RLS_SCOPE = text(
    "SELECT set_config('app.current_tenant', :tenant_id, true), "
    "set_config('app.bootstrap', :bootstrap, true)"
)


def scope_session_to_tenant(session: AsyncSession | Session, tenant_id: uuid.UUID) -> None:
    """Declara que toda transação desta sessão roda no escopo de um tenant.

    O tenant_id DEVE vir de um contexto autenticado (JWT) — nunca de input do
    usuário (CLAUDE.md, seção 7).

    Args:
        session: Sessão a escopar.
        tenant_id: Tenant dono dos dados que a sessão vai ler/escrever.
    """
    session.info[_TENANT_INFO_KEY] = str(tenant_id)
    session.info[_BOOTSTRAP_INFO_KEY] = False


def scope_session_to_auth_bootstrap(session: AsyncSession | Session) -> None:
    """Declara que esta sessão roda com o bypass de RLS de bootstrap de autenticação.

    O bypass é concedido pela policy `auth_bootstrap` apenas nas tabelas
    tenants/users — cases, audit_logs e demais tabelas de dados permanecem
    bloqueadas (ver `get_auth_bootstrap_session`).

    Args:
        session: Sessão a escopar.
    """
    session.info[_TENANT_INFO_KEY] = ""
    session.info[_BOOTSTRAP_INFO_KEY] = True


@event.listens_for(Session, "after_begin")
def _apply_rls_scope(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Aplica o escopo de RLS da sessão no início de cada transação.

    Roda a cada `begin` — ou seja, também depois de um `commit()`, quando a
    sessão pode ter trocado de conexão física (ver docstring do módulo). Uma
    sessão que não declarou escopo nenhum recebe "sem tenant, sem bootstrap",
    nunca o resíduo da request anterior naquela conexão.

    Args:
        session: Sessão que iniciou a transação.
        transaction: Transação recém-iniciada (não usado).
        connection: Conexão em que a transação foi aberta.
    """
    connection.execute(
        _APPLY_RLS_SCOPE,
        {
            "tenant_id": session.info.get(_TENANT_INFO_KEY, ""),
            "bootstrap": "true" if session.info.get(_BOOTSTRAP_INFO_KEY) else "false",
        },
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
        scope_session_to_tenant(session, tenant_id)
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
        Sessão SQLAlchemy assíncrona com app.bootstrap='true'.
    """
    async with async_session_factory() as session:
        scope_session_to_auth_bootstrap(session)
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
