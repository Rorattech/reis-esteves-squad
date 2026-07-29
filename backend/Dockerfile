# syntax=docker/dockerfile:1

# Python 3.13 — versão estável atual (suporte de segurança até ~2029)
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Build context é a raiz do repo (ver infra/docker-compose.yml) — não
# backend/ — porque backend/app/core/audit.py importa orchestrator/state.py
# (CaseState, AuditEntry) e os dois são pacotes irmãos no repo, não um
# subdiretório do outro. `pip install -e` só registra o pacote `app` no
# sys.path (packages.find include=["app*"] em pyproject.toml) — PYTHONPATH=/app
# é o que de fato torna `orchestrator` importável, já que ele também vira um
# subdiretório direto de /app depois do COPY abaixo.
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/tests ./tests
COPY orchestrator ./orchestrator
COPY prompts ./prompts

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000

# --reload habilita hot-reload; o código fonte é montado como volume em dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
