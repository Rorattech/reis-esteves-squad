# Auditoria Técnica — Fase 1 (Fundação) — Squad Digital

Data da auditoria: 2026-07-28
Escopo: leitura integral de `CLAUDE.md`, `docs/architecture.md`, `backend/pyproject.toml`,
`infra/docker-compose.yml`, migrations Alembic, `backend/app/`, `orchestrator/`, `prompts/`,
`infra/`, e busca por `tests/` em todo o repositório. Nenhum arquivo de código foi alterado.

## Veredito resumido

A Fase 1 cobre bem **autenticação, isolamento de tenant e RLS** — essa parte está sólida e
correta. Mas **três pilares que o CLAUDE.md declara obrigatórios para qualquer nó de grafo**
não existem ainda: utilitário de auditoria (`core/audit.py`), carregador de prompts em runtime
(`core/prompts.py`) e qualquer teste automatizado. Nenhum grafo LangGraph foi iniciado (apenas
o contrato de dados `CaseState` existe), o que é esperado para uma fase de fundação, mas deve
ficar explícito: **os módulos 1–6 não têm hoje nenhuma peça de orquestração para se conectar**,
só os alicerces (banco, auth, tenancy) e o contrato de estado.

---

## 1. Itens concluídos

| Item | Evidência |
|---|---|
| Docker Compose funcional (sintaxe válida) | `infra/docker-compose.yml` — `docker compose --env-file ../.env config` roda sem erro nem warning; healthchecks em `postgres` e `redis`; `backend`/`frontend` com `depends_on: condition: service_healthy` |
| Bootstrap de usuário não-superuser do Postgres | `infra/postgres/init-app-role.sh` cria `DB_USER` sem `SUPERUSER`, dono do banco — necessário porque superuser ignora RLS mesmo com `FORCE ROW LEVEL SECURITY` |
| Banco dedicado do n8n isolado | `infra/postgres/init-n8n-db.sh` cria usuário/banco próprios para o n8n, separados do banco da aplicação |
| `.env` local completo | Todas as chaves de `.env.example` (incl. todas as `N8N_*`) estão presentes em `.env`; `.env` está no `.gitignore` |
| Migrations Alembic | `backend/alembic/versions/0406e102877a_...py` cria `tenants`, `users`, `cases`, `audit_logs` com PK UUID, FKs corretas, índices em `tenant_id`/`case_id`/`user_id`, enums nativos do Postgres |
| `alembic/env.py` alinhado ao projeto | URL vem de `settings.database_url` (nunca hardcoded), `target_metadata = Base.metadata`, e `app/models/__init__.py` importa todos os modelos antes de qualquer autogenerate |
| Row Level Security | `ENABLE` + `FORCE ROW LEVEL SECURITY` em `tenants`, `users`, `cases`, `audit_logs`; policy `tenant_isolation` em todas; migration `3abdfd696724` endurece o cast `::uuid` contra `app.current_tenant = ''` (fail-closed) e cria policy `auth_bootstrap` restrita a `tenants`/`users` para registro/login pré-tenant |
| tenant_id presente e indexado | `Tenant`, `User`, `Case`, `AuditLog` (`backend/app/models/{tenant,user,case,audit_log}.py`) — todas as tabelas de negócio têm `tenant_id UUID NOT NULL` com FK e índice |
| Middleware de tenant | `backend/app/middleware/tenant.py` — extrai `tenant_id` do JWT, bloqueia com 403 se ausente/inválido, injeta `SET app.current_tenant` via `set_config` parametrizado (sem risco de injection), zera `app.bootstrap` a cada request para não vazar bypass de RLS entre requests que reusem a mesma conexão física |
| Autenticação JWT | `backend/app/api/v1/auth.py` + `backend/app/core/security.py` — `/register`, `/login`, `/refresh`, `/me`; bcrypt direto (não passlib, justificado em comentário); access token 15min / refresh 7 dias, ambos configuráveis via `Settings` |
| `CaseState` (`orchestrator/state.py`) | `TypedDict` com `case_id`, `tenant_id`, `status`, `current_module`, `human_approval_required`, `audit_trail` (equivalente a `audit_log`); sub-modelos `LegalSource` (com `hallucination_risk`), `StrategyMemo`/`DraftPetition` (com `DRAFT_PENDING_REVIEW`/`APPROVED`/`REJECTED` e `approved_by`/`approved_at`/`content_hash`), `AuditEntry` com todos os campos da seção 10 do CLAUDE.md |
| LangGraph sem LangChain | `backend/pyproject.toml` depende de `langgraph>=0.2`; nenhuma dependência `langchain*` no projeto |
| Estrutura de pastas de prompts | `prompts/_shared/{_base.md,output_format.md}` + `prompts/digital/_squad.md` + 12 arquivos de agente (2 intake + 2 evidence + 3 research + 2 strategy + 1 drafting + 2 review), todos com front matter YAML (exceto `_base.md`, exceção documentada) |
| Hygiene de repositório | `__pycache__/`, `*.egg-info/`, `node_modules/`, `.env` corretamente no `.gitignore` e nenhum desses artefatos está de fato versionado (`git ls-files` confirma) |

---

## 2. Itens parcialmente concluídos

| Item | O que existe | O que falta |
|---|---|---|
| RBAC | `UserRole` (admin/lawyer/paralegal/viewer) definido em `backend/app/models/enums.py`; `role` é emitido no JWT (`security.py`) e decodificado em `request.state.role` (`middleware/tenant.py:71`) | Nenhuma rota ou dependency verifica o valor de `role` — busca por `role` no código mostra que ele é apenas transportado, nunca comparado contra uma lista de papéis permitidos. Não há `require_role(...)`/equivalente em lugar nenhum |
| `audit_logs` (schema) | Tabela existe com `tenant_id`, `case_id`, `actor_id`, `action`, `input_hash`, `output_hash`, `agent_name`, `model_used`, `created_at` (migration `0406e102877a`) | Faltam as colunas que `AuditEntry` (`orchestrator/state.py:120-137`) e o CLAUDE.md seção 10 exigem: `actor` (`system`\|`agent`\|`human`), `module`, `tokens_used`, `duration_ms`, `metadata`. `agent_name` não é equivalente semântico de `module` (`ModuleName` é `intake`\|`evidence`\|... — `agent_name` seria o agente dentro do módulo) |
| Gestão de prompts | Estrutura de pastas e front matter corretos | (a) `last_updated` usa formato `YYYY-DD-MM` em vez de `YYYY-MM-DD` em pelo menos `prompts/digital/_squad.md:6`, `prompts/digital/intake/coordinator.md:6` e `prompts/digital/research/legislation.md:6` (verificado por amostragem — recomenda-se checar os 12 arquivos); (b) `prompts/digital/research/legislation.md` não tem as seções obrigatórias `## Inputs Necessários` e `## Restrições` da seção 11 do CLAUDE.md, e seu `## Output Esperado` usa um formato próprio em vez do template de `prompts/_shared/output_format.md` |
| `CaseState` vs. CLAUDE.md §9 | Campos centrais presentes | CLAUDE.md §9 lista `approved_by` e `approved_at` como campos obrigatórios do **CaseState** (não apenas dos artefatos). No código atual esses campos só existem dentro de `StrategyMemo`/`DraftPetition`, não no nível superior do `CaseState` — só há `human_approval_status` (`pending`\|`approved`\|`rejected`\|`na`) sem identificar quem aprovou nem quando, no nível do caso como um todo |
| pgvector | Imagem `pgvector/pgvector:0.8.5-pg16-trixie` em uso no `docker-compose.yml` | Nenhuma migration executa `CREATE EXTENSION IF NOT EXISTS vector`; nenhuma tabela/coluna vetorial existe ainda. A extensão está disponível na imagem, mas não habilitada no banco da aplicação |
| Multitenancy em endpoints futuros | `CaseCreate`/`CaseUpdate`/`CaseResponse` (`backend/app/models/schemas/case.py`) já excluem `tenant_id`/`user_id` do payload do cliente, por design | Não existe `backend/app/api/v1/cases.py` nem router registrado em `main.py` — o isolamento de tenant nunca foi exercitado em uma rota real além de `/auth/*` e `/me` |

---

## 3. Lacunas bloqueantes

Estas impedem ou comprometem diretamente o início dos módulos 1–6 (`orchestrator/graphs/*`):

1. **Sem utilitário de auditoria.** `backend/app/core/audit.py` não existe. CLAUDE.md §10
   exige a função `create_audit_entry(...)` e que "cada nó do grafo deve registrar uma entrada
   no `audit_log` antes de retornar". Hoje nenhum código do repositório grava em `audit_logs`
   (confirmado por busca — o único uso do modelo `AuditLog` é sua própria definição ORM). Sem
   essa peça, nenhum nó dos módulos seguintes tem como cumprir a regra crítica de auditoria.
2. **Schema de `audit_logs` incompatível com `AuditEntry`.** Mesmo escrevendo o utilitário
   acima, os campos `actor`, `module`, `tokens_used`, `duration_ms` e `metadata` do
   `AuditEntry` (`orchestrator/state.py`) não têm coluna correspondente na tabela — é preciso
   uma nova migration antes de qualquer persistência real de auditoria.
3. **Sem carregador de prompts em runtime.** `backend/app/core/prompts.py` não existe em
   nenhum lugar do backend. CLAUDE.md §11 exige "Carregue prompts em runtime com função
   utilitária em `core/prompts.py`". Sem isso, nenhum nó de agente consegue montar o prompt
   final (`_base.md` → `_squad.md` → `<módulo>/<agente>.md`) de forma versionada.
4. **Zero testes automatizados no repositório.** Nenhum `test_*.py`, nenhum diretório
   `tests/`. `pytest` está configurado (`pyproject.toml`, `asyncio_mode = "auto"`) e listado em
   `dev`, mas não há um único teste — nem para auth, nem para isolamento de tenant/RLS, nem
   para auditoria. CLAUDE.md §5 exige cobertura mínima de 80% nos módulos de agentes; a
   fundação que os sustenta está em 0%, sem qualquer rede de segurança contra regressão em
   RLS/JWT/multitenancy conforme novos módulos forem adicionados.
5. **RBAC não é aplicado (apenas transportado).** O papel do usuário trafega no JWT mas nunca
   é checado. Isso não impede tecnicamente o início dos módulos de IA, mas é crítico porque os
   módulos seguintes (em especial Review/Drafting) vão expor endpoints de **aprovação humana**
   — exatamente o ponto que CLAUDE.md §2 trata como regra absoluta. Sem enforcement de RBAC, um
   usuário `viewer` ou `paralegal` poderia, em tese, acionar rotas de aprovação assim que forem
   criadas, a menos que essa lacuna seja fechada antes.

Não classificado como lacuna bloqueante, mas registrado por relevância directa aos módulos
seguintes: **nenhum grafo LangGraph existe** (`orchestrator/` só tem `__init__.py` e
`state.py`; não há `graphs/`, `checkpoints.py`, nem `router.py`). Entendo isso como o próprio
objetivo dos "módulos posteriores" mencionados no pedido de auditoria, não como algo que a Fase
1 deveria ter entregue — mas registro porque a ordem de execução importa: os itens 1–4 acima
precisam existir *antes* do primeiro nó do primeiro grafo, senão o padrão exigido pelo
CLAUDE.md (auditoria + prompt versionado em cada nó) já nasce quebrado no Módulo 1 (Intake).

---

## 4. Arquivos envolvidos

```
CLAUDE.md
docs/architecture.md
backend/pyproject.toml
backend/Dockerfile
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/0406e102877a_create_tenants_users_cases_audit_logs_.py
backend/alembic/versions/3abdfd696724_add_auth_bootstrap_rls_policy.py
backend/app/main.py
backend/app/core/config.py
backend/app/core/db.py
backend/app/core/security.py
backend/app/core/logging.py
backend/app/middleware/tenant.py
backend/app/models/__init__.py
backend/app/models/base.py
backend/app/models/tenant.py
backend/app/models/user.py
backend/app/models/case.py
backend/app/models/audit_log.py
backend/app/models/enums.py
backend/app/models/schemas/auth.py
backend/app/models/schemas/case.py
backend/app/api/v1/auth.py
infra/docker-compose.yml
infra/postgres/init-app-role.sh
infra/postgres/init-n8n-db.sh
.env / .env.example
Makefile
orchestrator/__init__.py
orchestrator/state.py
prompts/_shared/_base.md
prompts/_shared/output_format.md
prompts/digital/_squad.md
prompts/digital/intake/coordinator.md
prompts/digital/research/legislation.md
frontend/package.json
frontend/src/app/{layout.tsx,page.tsx,globals.css}
```

Arquivos/diretórios esperados pela estrutura do CLAUDE.md §4 e **ausentes** hoje (confirmado
via busca no repositório inteiro):

```
backend/app/core/audit.py
backend/app/core/prompts.py
backend/app/agents/
backend/app/services/
backend/app/api/v1/cases.py
orchestrator/graphs/
orchestrator/checkpoints.py
orchestrator/router.py
tests/  (em qualquer nível — backend, orchestrator ou raiz)
```

---

## 5. Riscos técnicos

| Risco | Severidade | Detalhe |
|---|---|---|
| Auditoria jurídica não rastreável | Alto | Sem `core/audit.py` e sem schema completo em `audit_logs`, é impossível cumprir CLAUDE.md §10 assim que o primeiro nó de grafo for escrito — o risco é os módulos seguintes serem implementados *sem* essa peça e a lacuna virar dívida técnica espalhada por 6 módulos em vez de 1 ponto central |
| Falha silenciosa de autorização | Alto | RBAC "decorativo" (papel presente no token, nunca checado) é o tipo de gap que passa despercebido em code review superficial porque a peça de dados (enum `UserRole`) existe — só falta o enforcement. Risco concreto quando endpoints de aprovação humana forem expostos |
| Regressão não detectada em RLS/tenancy | Alto | Zero testes automatizados sobre a área mais crítica do sistema (CLAUDE.md trata violação de tenant como "bug crítico"). Qualquer refactor futuro em `TenantMiddleware`, `db.py` ou nas migrations de RLS não tem rede de segurança |
| Divergência de schema `AuditEntry` (Pydantic) vs. `AuditLog` (ORM) | Médio | Se alguém implementar `create_audit_entry` copiando ingenuamente os campos do `AuditEntry` para um `INSERT`, vai falhar em runtime por colunas inexistentes (`module`, `metadata`, `tokens_used`, `duration_ms`, `actor`) — melhor resolver via migration antes de qualquer código de nó ser escrito |
| pgvector inativo | Médio | Módulo 3 (Research/RAG) depende de busca vetorial; ativar a extensão e desenhar a tabela de embeddings agora (mesmo vazia) evita descobrir problemas de imagem/permissão só quando o módulo 3 começar |
| Prompts fora do padrão retroalimentam o modelo de forma inconsistente | Médio | `legislation.md` sem `## Restrições` significa que o agente de pesquisa legislativa não tem, no próprio prompt, o lembrete textual de não inventar fontes/sinalizar `hallucination_risk` — a garantia hoje depende só do schema Pydantic (`LegalSource.hallucination_risk`), não do prompt que instrui o modelo |
| Falta de rate limiting | Baixo (por ora) | CLAUDE.md §12 exige middleware de rate limiting em todas as rotas — ainda inexistente. Baixo risco imediato (poucas rotas expostas hoje), mas deve entrar no plano antes de abrir a API a mais tráfego |

---

## 6. Plano mínimo de correção (ordem de prioridade)

**P0 — antes de escrever o primeiro nó de qualquer módulo**

1. Criar `backend/app/core/audit.py` com `create_audit_entry(...)` seguindo exatamente a
   assinatura do CLAUDE.md §10.
2. Nova migration Alembic adicionando a `audit_logs`: `actor` (enum `system`\|`agent`\|`human`),
   `module` (enum `ModuleName`), `tokens_used` (int), `duration_ms` (int), `metadata` (JSONB) —
   e decidir formalmente a relação entre `agent_name` (já existente) e o `actor_id`/`module` do
   `AuditEntry`, documentando a decisão.
3. Testes automatizados mínimos (criar `backend/tests/` + configurar fixture de banco de
   teste): fluxo completo de `/auth/register` → `/login` → `/refresh` → `/me`; 403 do
   `TenantMiddleware` sem token/tenant inválido; isolamento cross-tenant via RLS (dois tenants,
   confirmar que a sessão de um nunca lê linha do outro). Esse é o piso mínimo antes de somar
   qualquer módulo novo, para não crescer dívida sobre uma base sem cobertura.
4. Implementar enforcement de RBAC — uma dependency FastAPI (`require_role(*roles)` ou
   equivalente) usando `request.state.role`, aplicada nas rotas conforme forem criadas.

**P1 — necessário para o Módulo 1 (Intake) arrancar**

5. Criar `backend/app/core/prompts.py` com carregamento versionado
   `_base.md → _squad.md → <módulo>/<agente>.md`, incluindo parsing do front matter.
6. Criar `orchestrator/graphs/`, `orchestrator/checkpoints.py` (persistência do `CaseState` em
   Postgres) e `orchestrator/router.py` (esqueleto mínimo — nem que só rotear para `intake`
   inicialmente).
7. Migration para `CREATE EXTENSION IF NOT EXISTS vector` (preparar terreno para o Módulo 3
   sem bloquear o time quando chegar lá).

**P2 — qualidade e conformidade antes de escalar para mais módulos**

8. Corrigir `last_updated` (`YYYY-MM-DD`) e completar `## Inputs Necessários` / `## Restrições`
   / `## Output Esperado` (alinhado a `prompts/_shared/output_format.md`) nos 12 arquivos de
   prompt do squad `digital` — revisão arquivo a arquivo, não só nos 3 amostrados aqui.
9. Adicionar `approved_by`/`approved_at` no nível do `CaseState` (não só dentro de
   `StrategyMemo`/`DraftPetition`) para fechar a aderência ao CLAUDE.md §9.
10. Middleware de rate limiting nas rotas de API (CLAUDE.md §12).
11. Implementar `backend/app/api/v1/cases.py` (schemas já prontos) quando o Módulo 1 precisar
    de endpoints de caso.
