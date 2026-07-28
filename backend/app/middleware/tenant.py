"""Middleware de multitenancy (CLAUDE.md, seção 7 — regra crítica).

Extrai o tenant_id do access token JWT em cada request, bloqueia com 403
qualquer request sem um tenant_id válido, e injeta `SET app.current_tenant`
na sessão do banco associada à request — segunda camada de isolamento via
Row Level Security (ver docs/architecture.md, seção 4).
"""

import uuid

import structlog
from fastapi import Request, Response, status
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.core.db import async_session_factory
from app.core.security import InvalidTokenError, TokenType, decode_token

logger = structlog.get_logger()

# Rotas públicas: ainda não existe tenant_id autenticado nelas.
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    }
)


class TenantMiddleware(BaseHTTPMiddleware):
    """Isola cada request ao tenant do usuário autenticado no access token."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Valida o tenant da request e escopa a sessão do banco antes do handler.

        Args:
            request: Request HTTP recebida.
            call_next: Próximo handler na cadeia (rota ou middleware seguinte).

        Returns:
            Response 403 se o tenant_id estiver ausente/inválido, ou a resposta
            normal da rota com `request.state.db` já escopado por tenant.
        """
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _forbidden("Token de autenticação ausente.")

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = decode_token(token, expected_type=TokenType.ACCESS)
        except InvalidTokenError:
            return _forbidden("Token de autenticação inválido ou expirado.")

        raw_tenant_id = payload.get("tenant_id")
        try:
            tenant_id = uuid.UUID(str(raw_tenant_id))
        except (TypeError, ValueError):
            return _forbidden("Token sem tenant_id válido.")

        request.state.tenant_id = str(tenant_id)
        request.state.user_id = payload.get("sub")
        request.state.role = payload.get("role")

        async with async_session_factory() as session:
            # set_config (não SET direto) permite parâmetro ligado com segurança
            # contra injection; is_local=False mantém o valor por toda a sessão,
            # que aqui vive apenas durante esta request. app.bootstrap é sempre
            # forçado a 'false' aqui: se esta conexão física já foi usada antes
            # por get_auth_bootstrap_session (pool reutiliza conexões), o bypass
            # de RLS daquela request não pode vazar para esta (app/core/db.py).
            await session.execute(
                text(
                    "SELECT set_config('app.current_tenant', :tenant_id, false), "
                    "set_config('app.bootstrap', 'false', false)"
                ),
                {"tenant_id": str(tenant_id)},
            )
            request.state.db = session
            return await call_next(request)


def _forbidden(detail: str) -> JSONResponse:
    logger.warning("tenant_middleware.blocked", detail=detail)
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": detail})
