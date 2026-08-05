SHELL := /bin/bash

# O docker-compose.yml fica em infra/ e o .env na raiz do projeto. O Docker Compose
# resolve --env-file relativo ao diretório de execução, então todo alvo roda a
# partir de infra/ referenciando ../.env — não mova esta convenção sem testar.
COMPOSE := cd infra && docker compose --env-file ../.env

.PHONY: help env up down down-v build rebuild restart ps logs \
        sh-backend sh-frontend sh-postgres sh-redis sh-n8n \
        psql redis-cli migrations test lint fmt clean \
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
