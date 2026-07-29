"""Rate limiting (CLAUDE.md, seção 12 — aplicar em todas as rotas de API).

Limite por IP do cliente, com o Redis do projeto (já usado como cache/broker
— ver docker-compose.yml) como storage compartilhado entre workers, para o
limite ser consistente mesmo com múltiplos processos uvicorn.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.backend_rate_limit_per_minute}/minute"],
    storage_uri=settings.redis_url,
)
