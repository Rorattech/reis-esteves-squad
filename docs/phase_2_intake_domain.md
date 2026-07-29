# Fase 2.1 — Camada de domínio de Intake e Roteamento

Documentação técnica do domínio implementado para a Fase 2 (ver
`docs/roadmap_mvp_squad_digital.md`, seção 2.1). Cobre apenas modelos,
migrations, schemas e serviços — os nós LangGraph (coordinator/triage) e a
API HTTP de intake são as próximas etapas (2.2 a 2.4).

## Entidades

| Tabela | Descrição | Arquivo do modelo |
|---|---|---|
| `clients` | Cliente (parte lesada) de um tenant. `document_number` é opcional e único por tenant quando presente. | `backend/app/models/client.py` |
| `cases` | Ganhou `client_id` (opcional), `area`/`matter` (classificação de triagem), `current_module` (etapa do fluxo LangGraph, default `intake`) e `human_review_required` (default `true`). | `backend/app/models/case.py` |
| `case_intakes` | Relato inicial estruturado — texto livre (`narrative`) + campos estruturados (valor envolvido, data do fato, BO, documentos que o cliente diz ter, informações pendentes). Relação 1:1 com `cases` via `UniqueConstraint(case_id)`. | `backend/app/models/case_intake.py` |
| `case_documents` | Item do checklist de documentos (`received`/`pending`/`waived`), com `origin` (de onde veio a exigência: intake, evidence, human_review — texto livre). | `backend/app/models/case_document.py` |

Todas as tabelas novas têm `tenant_id UUID NOT NULL`, RLS habilitada e
`FORCE ROW LEVEL SECURITY` com a policy `tenant_isolation` (mesmo padrão de
`0406e102877a`/`3abdfd696724`/`e5c113039c58`). Migration:
`backend/alembic/versions/41280d8b096c_add_clients_case_intakes_case_documents_.py`.

`audit_logs.case_id` passou a aceitar `NULL`: cadastro/edição de um cliente é
auditável antes de qualquer caso existir (`app/core/audit.py`,
`audit_entry_to_orm`).

## Por que a Fase 2 não guarda arquivos

O relato inicial (`case_intakes.claimed_documents`) guarda apenas os *nomes*
dos documentos que o cliente diz ter — nunca o arquivo em si. Upload,
armazenamento e OCR pertencem à Fase 3 (Evidências). `case_documents` é o
checklist (o que falta/chegou/foi dispensado), não o repositório de arquivos.

## Isolamento de tenant além de RLS

`cases.client_id` é uma FK para `clients.id`, mas a FK por si só não garante
isolamento de tenant — a RLS de `cases` só valida o `tenant_id` da própria
linha. Por isso `backend/app/api/v1/cases.py` (`_ensure_client_belongs_to_tenant`)
verifica explicitamente, antes de criar/atualizar um caso, que o `client_id`
informado pertence ao mesmo tenant do usuário autenticado — do contrário
retorna 404 (mesmo padrão de "não vazar existência" usado no resto da API).

## Serviços (`backend/app/services/`)

Cada serviço recebe `tenant_id` explícito (nunca inferido do payload),
valida que o registro pai pertence a esse tenant, e grava uma entrada em
`audit_logs` (actor `human`, `model_used="n/a"` — convenção do projeto para
ações sem chamada a modelo de IA, ver `backend/tests/test_audit.py`) antes de
commitar:

- `client_service.py` — `create_client`, `update_client`.
- `case_intake_service.py` — `get_intake`, `submit_intake` (cria ou substitui
  o relato do caso — idempotente por `case_id`), `update_intake` (PATCH).
- `case_document_service.py` — `list_checklist`, `add_checklist_item`,
  `update_checklist_item`.

`case_intake_service`/`case_document_service` são consumidos pela API HTTP
da Fase 2.4 (`app/api/v1/intake.py`, ver docs/intake_api.md);
`client_service` ainda não tem rota própria — permanece disponível para uma
futura tela de cadastro de clientes.

## Testes

- `tests/test_intake_domain_schemas.py` — validação dos schemas Pydantic
  (rejeição de payloads inválidos: nome vazio, e-mail inválido, valor
  negativo, enum inexistente).
- `tests/test_client_service.py`, `tests/test_case_intake_service.py`,
  `tests/test_case_document_service.py` — CRUD dos serviços, auditoria
  gravada, e isolamento de tenant a nível de serviço.
- `tests/test_intake_domain_tenant_isolation.py` — RLS a nível de banco nas
  três tabelas novas, e o guard de `client_id` cross-tenant na API de casos.

## Dados fictícios para desenvolvimento

`backend/alembic/versions/48c0ad76f3dd_seed_digital_squad_demo_cases.py`
popula o tenant de dev (`reis-esteves`, criado por `d27cf82e3178`) com 7
casos fictícios cobrindo os cenários principais do squad: Marketplace
(Mercado Livre e Facebook Marketplace), PIX (dois cenários — contato
clonado no WhatsApp e falso funcionário de banco), WhatsApp clonado, Shopee
e falso advogado. Cada caso vem com cliente, relato inicial (`case_intakes`)
e checklist de documentos (`case_documents`) já populados, para dar dados
reais o suficiente para testar intake, roteamento, lista de casos e
formulário sem depender de nenhum dado real de cliente.

Mesmas guardas de segurança da seed de tenant/admin (`d27cf82e3178`): só
roda com `BACKEND_ENV=development`, e é idempotente (UUIDs determinísticos
via `uuid5` + `ON CONFLICT ... DO NOTHING`) — seguro rodar
`alembic upgrade head` de novo num banco que já tem esses dados.

## API HTTP (Fase 2.4)

Endpoints de intake/checklist/execução/revisão/auditoria documentados em
docs/intake_api.md. `client_service.py` segue sem rota própria.
