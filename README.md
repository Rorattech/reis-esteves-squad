# Squad Digital — Reis Esteves Advocacia

Copiloto de IA para o Squad Digital do escritório Reis Esteves Advocacia: um sistema
multiagente que apoia advogados na análise de casos de Direito Digital (fraudes em
plataformas, golpes de PIX, responsabilidade de provedores de internet).

## Objetivo

O sistema **nunca substitui o advogado** — ele auxilia. Todo output jurídico gerado por
IA (pesquisa, estratégia, minuta) carrega status `DRAFT_PENDING_REVIEW` até que um
advogado humano aprove explicitamente. Human-in-the-loop é regra absoluta do projeto,
não um detalhe de implementação (ver [`CLAUDE.md`](./CLAUDE.md), seção 2).

O workflow é dividido em 6 módulos orquestrados via LangGraph:

1. **Intake** — triagem e roteamento do caso
2. **Evidence** — análise de provas digitais
3. **Research** — pesquisa jurídica (legislação, jurisprudência, doutrina)
4. **Strategy** — estratégia processual
5. **Drafting** — redação da petição (esqueleto + minuta)
6. **Review** — revisão de qualidade e aprovação humana

Cada escritório de advocacia é um tenant isolado (multitenancy obrigatória, reforçada
por Row Level Security no Postgres).

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose v2
- [GNU Make](https://www.gnu.org/software/make/) — usado pelos comandos `make` deste
  README (`make up`, `make migrations` etc.). Já vem instalado por padrão no macOS e na
  maioria das distribuições Linux; para conferir, rode `make --version`. Se não tiver:
  - **macOS:** instale as Command Line Tools com `xcode-select --install` (ou via
    [Homebrew](https://brew.sh/): `brew install make`)
  - **Linux (Debian/Ubuntu):** `sudo apt install make`
  - **Windows:** use o [WSL](https://learn.microsoft.com/windows/wsl/install) (recomendado)
    ou instale via [Chocolatey](https://chocolatey.org/): `choco install make`
- Isso é suficiente para rodar o projeto inteiro. Para desenvolver fora do container
  (ex.: rodar `pytest`/`next dev` direto no host):
  - Python 3.13+ (backend)
  - Node.js 20.9+ (frontend)

## Stack técnica

| Camada           | Tecnologia                                                  |
|------------------|---------------------------------------------------------------|
| Backend          | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async)   |
| Orquestração IA  | LangGraph                                                    |
| Banco            | PostgreSQL 16 + pgvector, com Row Level Security por tenant  |
| Migrations       | Alembic                                                      |
| Cache / rate limit | Redis                                                      |
| Automação        | n8n self-hosted (tarefas de background — OCR, notificações; nunca exposto ao frontend) |
| Frontend         | Next.js 16 (App Router), TypeScript estrito, Tailwind CSS, Zustand, react-hook-form + zod |
| Auth             | JWT (access + refresh token), RBAC (admin / lawyer / paralegal / viewer) |
| Infra local      | Docker Compose                                               |

Mais detalhes de arquitetura em [`docs/architecture.md`](./docs/architecture.md) e nas
regras de desenvolvimento em [`CLAUDE.md`](./CLAUDE.md).

## Como subir o ambiente de desenvolvimento

```bash
# 1. Clone o repositório e entre na pasta
git clone <url-do-repo>
cd reis-esteves-squad

# 2. Suba todos os serviços (cria o .env a partir do .env.example na primeira vez)
make up
```

Isso builda e sobe backend, frontend, Postgres, Redis e n8n. Depois:

```bash
# 3. Aplique as migrations (cria o schema + RLS + tenant de teste + casos de exemplo, ver abaixo)
make migrations
```

Serviços disponíveis:

| Serviço   | URL                              |
|-----------|-----------------------------------|
| Frontend  | http://localhost:3000             |
| Backend   | http://localhost:8000              |
| API docs  | http://localhost:8000/docs         |
| n8n       | http://localhost:5678 (uso interno) |

### Login de teste

As migrations já semeiam um tenant, um usuário admin e 7 casos fictícios do Squad
Digital para testes manuais (só em `BACKEND_ENV=development`, nunca em produção):

- **E-mail:** `admin@reisesteves.com.br`
- **Senha:** `ReisEsteves2026!`

### Comandos úteis (`make help` lista todos)

```bash
make ps            # status dos containers
make logs-backend  # logs de um serviço específico
make sh-backend    # shell dentro do container do backend
make migrations    # aplica as migrations do Alembic (rode de novo após atualizar o código)
make test          # roda a suíte de testes do backend (pytest)
make lint          # ruff (backend) + eslint (frontend)
make fmt           # formata o backend com black
make down          # para os containers (mantém os dados)
```

### Variáveis de ambiente

Copiadas de [`.env.example`](./.env.example) para `.env` automaticamente pelo `make up`
(ou manualmente via `make env`). Nunca commite o `.env` — ele já está no
`.gitignore`. Chaves de modelos de IA (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` etc.)
ficam em branco por padrão; preencha as que for usar.

## Estrutura do projeto

```
backend/         # API FastAPI (app/), migrations (alembic/), testes (tests/)
orchestrator/     # Grafos LangGraph, estado do caso (CaseState) e checkpoints
prompts/          # Prompts versionados por squad/módulo/agente
frontend/         # Next.js App Router
infra/            # Docker Compose, configuração do Postgres
docs/             # Arquitetura e ADRs
```

Detalhes da estrutura, convenções de código e regras de multitenancy/auditoria estão em
[`CLAUDE.md`](./CLAUDE.md).
