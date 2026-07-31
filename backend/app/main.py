"""Ponto de entrada da aplicação FastAPI."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.cases import router as cases_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.intake import router as intake_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.middleware.tenant import TenantMiddleware

configure_logging()
logger = structlog.get_logger()

app = FastAPI(title="Squad Digital API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Ordem importa: o último middleware adicionado é o mais externo. CORS fica
# por fora de tudo (headers presentes até em resposta de rate limit/403), o
# rate limit fica por fora do TenantMiddleware (rejeita antes de decodificar
# JWT), TenantMiddleware é o mais interno.
app.add_middleware(TenantMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(cases_router, prefix="/api/v1")
app.include_router(intake_router, prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Verifica se a API está operacional.

    Returns:
        Dicionário com status da aplicação.
    """
    return {"status": "ok"}
