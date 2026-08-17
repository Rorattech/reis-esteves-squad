SHELL := /bin/bash

# O docker-compose.yml fica em infra/ e o .env na raiz do projeto. O Docker Compose
# resolve --env-file relativo ao diretório de execução, então todo alvo roda a
# partir de infra/ referenciando ../.env — não mova esta convenção sem testar.
COMPOSE := cd infra && docker compose --env-file ../.env

# Stack de produção (VPS) — arquivo próprio, não um override do de dev: portas
# publicadas e bind mounts do dev precisam SUMIR, e o merge do Compose sabe
# adicionar, não remover. Ver docs/adr/0004-deploy-hostinger-netlify.md.
COMPOSE_PROD := cd infra && docker compose --env-file ../.env -f docker-compose.prod.yml

.PHONY: help env up down down-v build rebuild restart ps logs \
        sh-backend sh-frontend sh-postgres sh-redis sh-n8n \
        psql redis-cli migrations test lint fmt clean \
        prod-up prod-down prod-ps prod-logs prod-migrations prod-backup \
        graph graph-update graph-watch graph-watch-stop graph-report

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## Cria .env a partir de .env.example (não sobrescreve se já existir)
	@test -f .env || (cp .env.example .env && echo ".env criado a partir de .env.example — edite os valores antes de subir em produção")

up: env ## Builda as imagens (se preciso) e sobe todos os serviços em background
	$(COMPOSE) up -d --build

migrations: ## Aplica as migrations do Alembic (schema + RLS + tenant/admin de teste + casos de exemplo)
	$(COMPOSE) exec backend alembic upgrade head

down: ## Para e remove os containers (mantém os volumes)
	$(COMPOSE) down

down-v: ## Para os containers e APAGA os volumes (destrutivo — perde dados do Postgres/Redis/n8n)
	$(COMPOSE) down -v

build: ## Builda as imagens de backend e frontend
	$(COMPOSE) build

rebuild: ## Builda as imagens sem usar cache
	$(COMPOSE) build --no-cache

restart: ## Reinicia todos os serviços
	$(COMPOSE) restart

ps: ## Lista os containers do projeto e seus status
	$(COMPOSE) ps

logs: ## Segue os logs de todos os serviços (use logs-<serviço> para um específico)
	$(COMPOSE) logs -f

logs-%: ## Segue os logs de um serviço específico, ex: make logs-backend
	$(COMPOSE) logs -f $*

sh-backend: ## Abre um shell (bash) dentro do container do backend
	$(COMPOSE) exec backend bash

sh-frontend: ## Abre um shell (sh) dentro do container do frontend
	$(COMPOSE) exec frontend sh

sh-postgres: ## Abre um shell (bash) dentro do container do Postgres
	$(COMPOSE) exec postgres bash

sh-redis: ## Abre um shell (sh) dentro do container do Redis
	$(COMPOSE) exec redis sh

sh-n8n: ## Abre um shell (sh) dentro do container do n8n
	$(COMPOSE) exec n8n sh

psql: ## Abre um psql conectado ao banco da aplicação
	$(COMPOSE) exec postgres bash -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

redis-cli: ## Abre um redis-cli autenticado
	$(COMPOSE) exec redis sh -c 'redis-cli -a "$$REDIS_PASSWORD"'

test: ## Roda a suíte de testes do backend (pytest)
	$(COMPOSE) exec backend pytest

lint: ## Roda o lint do backend (ruff) e do frontend (eslint)
	$(COMPOSE) exec backend ruff check .
	$(COMPOSE) exec frontend npm run lint

fmt: ## Formata o código do backend (black)
	$(COMPOSE) exec backend black .

clean: down-v ## Alias de down-v — para os containers e apaga os volumes

# --- Produção (rodar NA VPS) — ver docs/adr/0004-deploy-hostinger-netlify.md ---
# O frontend não está aqui: é buildado e servido pela Netlify.

prod-up: ## [VPS] Builda e sobe o stack de produção (backend, banco, redis, n8n, caddy)
	$(COMPOSE_PROD) up -d --build

prod-down: ## [VPS] Para o stack de produção (mantém os volumes)
	$(COMPOSE_PROD) down

prod-ps: ## [VPS] Status dos containers de produção
	$(COMPOSE_PROD) ps

prod-logs: ## [VPS] Segue os logs do stack de produção
	$(COMPOSE_PROD) logs -f --tail=100

prod-migrations: ## [VPS] Aplica as migrations do Alembic em produção
	$(COMPOSE_PROD) exec backend alembic upgrade head

prod-backup: ## [VPS] Dump do Postgres + tar das evidências em ./backups (rode os dois JUNTOS)
	@mkdir -p backups
	@set -euo pipefail; \
	STAMP=$$(date +%Y%m%d-%H%M%S); \
	$(COMPOSE_PROD) exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' \
	  | gzip > "$(CURDIR)/backups/postgres-$$STAMP.sql.gz"; \
	$(COMPOSE_PROD) exec -T backend tar czf - -C /app/storage/evidence . \
	  > "$(CURDIR)/backups/evidence-$$STAMP.tar.gz"; \
	echo "backup gerado: backups/postgres-$$STAMP.sql.gz + backups/evidence-$$STAMP.tar.gz"
# Os dois artefatos saem em STREAM para stdout e o redirecionamento cria o
# arquivo no host: quem escreve é o shell (usuário deploy), não o container.
# Montar ./backups dentro do container não funcionaria — o backend roda como
# appuser (uid 10001) e não tem permissão de escrita num diretório do host.
# `set -e` + `pipefail` garantem que uma falha no pg_dump não deixe para trás um
# .gz truncado passando por backup válido.

# --- Graphify (grafo de conhecimento do projeto) — ver docs/graphify.md ---------
# A chave da API vive em ~/.graphify/env (chmod 600), nunca no repositório.
GRAPHIFY_ENV := [ -f "$$HOME/.graphify/env" ] && source "$$HOME/.graphify/env";
GRAPHIFY_PID := $$HOME/.graphify/watch-reis-esteves.pid

graph-update: ## Atualiza o grafo a partir do código (AST local, sem custo de API)
	graphify update .

graph: ## Reconstrói o grafo completo incluindo docs (usa a API do Gemini, ~4 centavos de dólar)
	$(GRAPHIFY_ENV) graphify extract . --backend gemini

graph-report: ## Regera GRAPH_REPORT.md e renomeia as comunidades
	$(GRAPHIFY_ENV) graphify cluster-only .

graph-watch: ## Sobe o watcher que atualiza o grafo a cada mudança de código
	@$(GRAPHIFY_ENV) nohup graphify watch . > "$$HOME/.graphify/watch-reis-esteves.log" 2>&1 & \
	 echo $$! > $(GRAPHIFY_PID); \
	 echo "watcher iniciado (PID $$(cat $(GRAPHIFY_PID))) — log em ~/.graphify/watch-reis-esteves.log"

graph-watch-stop: ## Para o watcher do grafo
	@if [ -f $(GRAPHIFY_PID) ]; then \
	   kill "$$(cat $(GRAPHIFY_PID))" 2>/dev/null && echo "watcher parado"; \
	   rm -f $(GRAPHIFY_PID); \
	 else echo "nenhum watcher registrado"; fi
