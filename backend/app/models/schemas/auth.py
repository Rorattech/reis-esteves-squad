"""Schemas Pydantic do fluxo de autenticação (registro, login, tokens, usuário atual)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole

# bcrypt trunca/rejeita senhas acima de 72 bytes UTF-8 — ver app/core/security.py.
_MAX_PASSWORD_BYTES = 72


def _validate_password_byte_length(password: str) -> str:
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"A senha deve ter no máximo {_MAX_PASSWORD_BYTES} bytes (UTF-8).")
    return password


class RegisterRequest(BaseModel):
    """Dados para criação de um novo tenant com seu usuário admin inicial."""

    tenant_name: str = Field(min_length=2, max_length=255)
    tenant_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=72)

    _validate_admin_password_bytes = field_validator("admin_password")(
        _validate_password_byte_length
    )


class LoginRequest(BaseModel):
    """Credenciais para autenticação de um usuário existente."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Refresh token usado para renovar o access token."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Par de tokens JWT emitido no login ou renovado no refresh."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Representação pública de um usuário — nunca inclui hashed_password."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: UserRole
    created_at: datetime
