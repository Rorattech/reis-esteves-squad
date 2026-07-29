"""Enforcement de RBAC (CLAUDE.md, seção 12 — admin | lawyer | paralegal | viewer).

TenantMiddleware (app/middleware/tenant.py) já decodifica o JWT e injeta o
papel do usuário em `request.state.role` — este módulo é o que de fato
compara esse papel contra os permitidos em cada rota, via
`Depends(require_role(...))`.
"""

from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.models.enums import UserRole


def require_role(*allowed_roles: UserRole) -> Callable[[Request], None]:
    """Cria uma dependency FastAPI que restringe uma rota a papéis específicos.

    Args:
        *allowed_roles: Papéis autorizados a acessar a rota (ex.: UserRole.ADMIN).

    Returns:
        Dependency que levanta 403 se `request.state.role` não estiver entre
        os papéis permitidos, ou se a rota não passou pelo TenantMiddleware
        (nenhum papel autenticado disponível).
    """
    allowed = {role.value for role in allowed_roles}

    def _check_role(request: Request) -> None:
        role = getattr(request.state, "role", None)
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Usuário não tem papel autorizado para executar esta ação.",
            )

    return _check_role
