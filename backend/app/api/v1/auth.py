"""Rotas de autenticação: registro, login, refresh e usuário atual.

Register, login e refresh são rotas públicas (sem tenant_id ainda conhecido) e
usam `get_auth_bootstrap_session` — a única sessão com bypass de RLS (restrito
às tabelas tenants/users, ver app/core/db.py) capaz de criar o primeiro tenant
ou localizar um usuário antes de qualquer tenant_id autenticado existir. `/me`
é protegida pelo TenantMiddleware, que já injeta a sessão escopada por tenant
em `request.state.db` (ver app/middleware/tenant.py).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_auth_bootstrap_session
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.models.tenant import Tenant
from app.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_auth_bootstrap_session),
) -> User:
    """Cria um novo tenant (escritório) com seu primeiro usuário, papel admin.

    Args:
        payload: Nome/slug do tenant e credenciais do usuário admin inicial.
        session: Sessão com bypass de RLS restrito a tenants/users (rota pública
            de bootstrap — ver get_auth_bootstrap_session em app/core/db.py).

    Returns:
        Usuário admin recém-criado.

    Raises:
        HTTPException: 409 se o slug do tenant já estiver em uso.
    """
    existing_tenant = await session.scalar(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    if existing_tenant is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug de tenant já está em uso.")

    tenant = Tenant(name=payload.tenant_name, slug=payload.tenant_slug)
    session.add(tenant)
    await session.flush()

    admin_user = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        role=UserRole.ADMIN,
    )
    session.add(admin_user)
    await session.commit()
    await session.refresh(admin_user)

    logger.info("auth.register", tenant_id=str(tenant.id), user_id=str(admin_user.id))
    return admin_user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_auth_bootstrap_session),
) -> TokenResponse:
    """Autentica um usuário por e-mail e senha, emitindo access e refresh tokens.

    Args:
        payload: E-mail e senha em texto puro.
        session: Sessão com bypass de RLS restrito a tenants/users (rota pública
            de bootstrap — ver get_auth_bootstrap_session em app/core/db.py).

    Returns:
        Access token (15min) e refresh token (7 dias).

    Raises:
        HTTPException: 401 se as credenciais forem inválidas.
    """
    # email é único por tenant (UniqueConstraint em User), não globalmente — o
    # mesmo e-mail pode existir em escritórios diferentes. Sem um identificador
    # de tenant no login, testamos a senha contra cada conta com esse e-mail.
    candidates = (await session.scalars(select(User).where(User.email == payload.email))).all()
    user = next(
        (u for u in candidates if verify_password(payload.password, u.hashed_password)), None
    )
    if user is None:
        logger.warning("auth.login_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")

    logger.info("auth.login", user_id=str(user.id), tenant_id=str(user.tenant_id))
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
        ),
        refresh_token=create_refresh_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_auth_bootstrap_session),
) -> TokenResponse:
    """Renova o access token a partir de um refresh token válido.

    Args:
        payload: Refresh token emitido no login.
        session: Sessão com bypass de RLS restrito a tenants/users (rota pública
            de bootstrap — ver get_auth_bootstrap_session em app/core/db.py).

    Returns:
        Novo access token; o refresh token original não é rotacionado.

    Raises:
        HTTPException: 401 se o refresh token for inválido/expirado ou o
            usuário associado não existir mais.
    """
    try:
        claims = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou expirado."
        ) from exc

    user = await session.get(User, uuid.UUID(claims["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")

    logger.info("auth.refresh", user_id=str(user.id))
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request) -> User:
    """Retorna os dados do usuário autenticado na request atual.

    tenant_id e user_id já foram validados pelo TenantMiddleware, que também
    injetou a sessão do banco escopada por tenant em `request.state.db`.

    Args:
        request: Request HTTP corrente, com `state.db`, `state.tenant_id` e
            `state.user_id` definidos pelo TenantMiddleware.

    Returns:
        Dados do usuário autenticado.

    Raises:
        HTTPException: 404 se o usuário do token não existir no tenant atual.
    """
    session: AsyncSession = request.state.db
    user = await session.scalar(
        select(User).where(
            User.tenant_id == uuid.UUID(request.state.tenant_id),
            User.id == uuid.UUID(request.state.user_id),
        )
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return user
