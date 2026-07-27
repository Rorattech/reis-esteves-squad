"""Ponto de entrada da aplicação FastAPI."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
logger = structlog.get_logger()

app = FastAPI(title="Squad Digital API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Verifica se a API está operacional.

    Returns:
        Dicionário com status da aplicação.
    """
    return {"status": "ok"}
