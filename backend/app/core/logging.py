"""Configuração de logging estruturado com structlog. Proibido usar print()."""

import logging
import sys

import structlog


def configure_logging() -> None:
    """Configura structlog para emitir logs em JSON estruturado."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
