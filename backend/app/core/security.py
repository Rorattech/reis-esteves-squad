"""Hashing de senhas (bcrypt) e emissão/validação de tokens JWT (CLAUDE.md, seção 12).

Usa a lib `bcrypt` diretamente (não passlib — passlib está sem manutenção desde
2020 e é incompatível com bcrypt >=4.1, ver https://github.com/pyca/bcrypt/issues/684).
"""

import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# Limite físico do algoritmo bcrypt — bytes além do 72º são ignorados/rejeitados.
_MAX_PASSWORD_BYTES = 72


class TokenType(StrEnum):
    """Distingue access token de refresh token dentro do claim "type" do JWT."""

    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """Levantada quando um token JWT é inválido, expirado ou do tipo incorreto."""


def hash_password(password: str) -> str:
    """Gera o hash bcrypt de uma senha em texto puro.

    Args:
        password: Senha em texto puro informada pelo usuário (máx. 72 bytes UTF-8).

    Returns:
        Hash bcrypt pronto para persistência em User.hashed_password.

    Raises:
        ValueError: Se a senha exceder 72 bytes em UTF-8 (limite físico do bcrypt).
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Senha excede o limite de {_MAX_PASSWORD_BYTES} bytes do bcrypt.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash armazenado.

    Args:
        plain_password: Senha em texto puro informada no login.
        hashed_password: Hash bcrypt armazenado em User.hashed_password.

    Returns:
        True se a senha confere, False caso contrário (inclusive em hash malformado).
    """
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _create_token(
    *,
    subject: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload, settings.backend_secret_key, algorithm=settings.backend_jwt_algorithm
    )


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    """Cria um access token de curta duração (default: 15 minutos).

    Args:
        user_id: ID do usuário autenticado.
        tenant_id: ID do tenant ao qual o usuário pertence.
        role: Papel RBAC do usuário (admin, lawyer, paralegal, viewer).

    Returns:
        Access token JWT assinado.
    """
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        role=role,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.backend_jwt_access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    """Cria um refresh token de longa duração (default: 7 dias).

    Args:
        user_id: ID do usuário autenticado.
        tenant_id: ID do tenant ao qual o usuário pertence.
        role: Papel RBAC do usuário (admin, lawyer, paralegal, viewer).

    Returns:
        Refresh token JWT assinado.
    """
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        role=role,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.backend_jwt_refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decodifica e valida um token JWT, garantindo assinatura, expiração e tipo.

    Args:
        token: Token JWT recebido (access ou refresh).
        expected_type: Tipo esperado do token (TokenType.ACCESS ou TokenType.REFRESH).

    Returns:
        Payload decodificado do token.

    Raises:
        InvalidTokenError: Se o token for inválido, expirado ou de tipo incorreto.
    """
    try:
        payload = jwt.decode(
            token,
            settings.backend_secret_key,
            algorithms=[settings.backend_jwt_algorithm],
            # PyJWT >= 2.10 rejeita iat "no futuro"; sem leeway, um salto de
            # relógio para trás (correção NTP da VM do Docker/WSL2 — saltos de
            # ~40s já observados neste ambiente) invalida tokens recém-emitidos
            # de forma intermitente. 60s de tolerância cobre essas correções
            # sem afrouxar a expiração de forma relevante (exp de 15min).
            leeway=60,
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token inválido ou expirado.") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Token não é do tipo esperado ({expected_type.value}).")

    return payload
