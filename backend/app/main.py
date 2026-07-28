"""Ponto de entrada da aplicação FastAPI."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.tenant import TenantMiddleware

configure_logging()
logger = structlog.get_logger()

app = FastAPI(title="Squad Digital API", version="0.1.0")

# Ordem importa: o último middleware adicionado é o mais externo, então CORS
# fica por fora do TenantMiddleware e trata preflight/headers antes dele.
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Verifica se a API está operacional.

    Returns:
        Dicionário com status da aplicação.
    """
    return {"status": "ok"}
