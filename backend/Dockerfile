# syntax=docker/dockerfile:1

# Dois alvos a partir da mesma base (ver docs/adr/0004-deploy-hostinger-netlify.md):
#   --target dev  -> hot-reload + pytest, usado por infra/docker-compose.yml
#   --target prod -> sem reload, sem dev deps, usado por infra/docker-compose.prod.yml
# O alvo é OBRIGATÓRIO nos dois compose: sem `target`, o Docker builda o último
# estágio do arquivo, e um deploy de produção sairia com --reload ligado.

# Python 3.13 — versão estável atual (suporte de segurança até ~2029)
FROM python:3.13-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Sem pacotes de sistema: o OCR é gerenciado (Google Cloud Vision — ver
# app/core/vision.py e docs/adr/0003-ocr-google-cloud-vision.md), e a Vision API
# aceita PDF inline, então nada precisa ser rasterizado localmente. Antes desta
# fase, tesseract-ocr, tesseract-ocr-por e poppler-utils eram instalados aqui.

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
COPY orchestrator ./orchestrator
COPY prompts ./prompts

EXPOSE 8000


# ------------------------------------------------------------------------------
# dev — hot-reload, dependências de teste, código montado como volume
# ------------------------------------------------------------------------------
FROM base AS dev

COPY backend/tests ./tests

RUN pip install --no-cache-dir ".[dev]"

# --reload habilita hot-reload; o código fonte é montado como volume em dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ------------------------------------------------------------------------------
# prod — sem reload, sem dev deps, código assado na imagem, usuário sem root
# ------------------------------------------------------------------------------
FROM base AS prod

RUN pip install --no-cache-dir "."

# O processo não roda como root: se o backend for comprometido, o atacante não
# ganha o container. O diretório de evidências é montado como volume e precisa
# ser gravável por este usuário (ver infra/docker-compose.prod.yml).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/storage/evidence \
    && chown -R appuser:appuser /app/storage
USER appuser

# BACKEND_WORKERS: 2 é o padrão para a KVM 2 (2 vCPU). O rate limit usa Redis
# como storage compartilhado (app/core/rate_limit.py), então múltiplos workers
# mantêm o limite consistente — não migre para storage em memória.
ENV BACKEND_WORKERS=2

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${BACKEND_WORKERS}"]
