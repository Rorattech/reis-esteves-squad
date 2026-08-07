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
da Fase 2.4 (`app/api/v1/intake.py`, ver docs/intake_api.md); `client_service`
é consumido por `app/api/v1/clients.py` (Fase 2.7, abaixo).

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
docs/intake_api.md.

---

# Fase 2.7 — Cliente, identificadores legíveis e catálogos

Retrabalho da abertura de caso. Decisões e alternativas rejeitadas em
[`docs/adr/0004-identificadores-legiveis-e-catalogos-de-classificacao.md`](./adr/0004-identificadores-legiveis-e-catalogos-de-classificacao.md).

## O problema

O modelo `Client` existia desde `41280d8b096c`, com serviço e schemas
auditados, mas **sem rota HTTP e sem tela**. Na prática o formulário de novo
caso pedia ao advogado que colasse um UUID à mão ("Token do cliente") e a
lista de casos exibia esse UUID na coluna "Cliente". Além disso a plataforma
era texto livre (três grafias viravam três plataformas) enquanto a modalidade
era um enum fechado de cinco valores — o inverso do que o produto precisa.

## Identificadores

| Série | Formato | Reinicia por ano |
|---|---|---|
| Caso | `CAS-2026-000123` | sim |
| Cliente | `CLI-000042` | não |

Emitidos por `app/core/identifiers.py`, contados por escritório em
`tenant_counters` (uma `SEQUENCE` do Postgres é global e faria o segundo
escritório começar de onde o primeiro parou). A alocação é uma única
instrução `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, cujo row lock
serializa requests concorrentes; o ano vem de `America/Sao_Paulo`.

O UUID continua sendo PK e o que aparece na URL — **nunca é exibido**.

## Qualificação do cliente

`clients` ganhou `code`, `person_type` (PF/PJ), RG + órgão emissor,
nascimento, nacionalidade, estado civil, profissão e endereço completo. São
os campos que a petição inicial exige (CPC art. 319, II), e o município/UF é
o que fixa o foro do consumidor (CDC art. 101, I).

CPF/CNPJ são validados por dígito verificador e **normalizados para só
dígitos** (`app/core/documents.py`, espelhado em
`frontend/src/lib/documents.ts`): sem isso, `529.982.247-25` e `52998224725`
passariam como clientes diferentes na checagem de duplicidade.

### Segurança — CPF não é credencial

CPF/CNPJ é **chave de vinculação interna, nunca fator de autenticação**. CPF
no Brasil é dado amplamente vazado: um portal futuro que libere o dossiê a
quem "informar o CPF" seria incidente de LGPD, não funcionalidade. A
autenticação de um cliente exigirá posse verificada (OTP no telefone/e-mail
cadastrado) ou token por caso emitido pelo advogado.

E a distinção que costuma confundir: mesmo quando o **processo judicial** é
público (CPC art. 189), o **dossiê neste sistema** — evidências, estratégia,
minuta — é coberto por sigilo profissional (EOAB art. 34, VII) e não é
público em hipótese alguma.

## Catálogos de classificação

`platforms` e `fraud_modalities` (`app/models/catalog.py`), com
`tenant_id NOT NULL` + RLS como toda tabela do projeto. Semeadas a partir de
`app/core/catalog_defaults.py` sob demanda, na primeira leitura do catálogo
(`ensure_catalog_seeded`) — reconciliando **por slug**, então entradas novas
no arquivo de defaults chegam a escritórios antigos sem migration.

Cada modalidade declara uma `family` do enum `FraudType` existente. O
escritório cadastra "golpe da falsa central de atendimento" e diz que é da
família `pix`; grafo e prompts continuam raciocinando sobre as cinco
famílias que conhecem. `cases.platform` (texto) e `cases.fraud_type` (enum)
permanecem como rótulo e família **denormalizados** — derivados, nunca
escritos direto.

## Efeitos no fluxo do caso

- `CaseCreate` aceita `client_id` (existente) **ou** `client` (novo,
  cadastrado na mesma transação do caso — um caso que falha não deixa
  cliente órfão). Os dois juntos são 422.
- A busca de casos e de clientes foi para o servidor: passou a incluir o
  nome do cliente, e filtrar no navegador exigiria baixar a base inteira com
  os nomes. **É `POST .../search`, com o termo no corpo** — query string vaza
  para access log do servidor, histórico do navegador, cabeçalho Referer e
  cache de proxy, e o termo pode ser um CPF ou um nome (CLAUDE.md, seção 12).
  Os `GET` continuam existindo para listagem simples, sem termo.
- A triagem **não escreve mais** `platform`/`fraud_type` no caso
  (`orchestrator/graphs/intake.py`): ela recomenda, e a classificação só
  muda por correção humana explícita com `platform_id`/`fraud_modality_id`
  (CLAUDE.md, seção 2).
- `CaseState` ganhou `case_code`, `client_city` e `client_state` — e nada
  além disso. Nome, CPF, RG e endereço completo nunca vão para o modelo de
  IA; o cabeçalho dos relatórios usa o código do caso.

## Rotas

| Método | Rota | Papel |
|---|---|---|
| POST | `/api/v1/clients` | admin / lawyer / paralegal |
| POST | `/api/v1/clients/search` | autenticado (termo no corpo) |
| GET | `/api/v1/clients?limit=` | autenticado (sem termo) |
| GET | `/api/v1/clients/{id}` | autenticado |
| PATCH | `/api/v1/clients/{id}` | admin / lawyer / paralegal |
| POST | `/api/v1/cases/search` | autenticado (termo no corpo) |
| GET \| POST | `/api/v1/catalog/platforms` | GET autenticado, POST operacional |
| GET \| POST | `/api/v1/catalog/fraud-modalities` | GET autenticado, POST operacional |

`CaseResponse` ganhou `code`, `client` (`ClientSummary` — id, código e nome,
**sem documento**), `platform_entry` e `fraud_modality`. As rotas que a
devolvem precisam de `CASE_RESPONSE_RELATIONSHIPS` (`app/api/v1/cases.py`):
sem o eager load, o Pydantic dispara lazy load em contexto async e estoura
`MissingGreenlet`.

## Interface

- `/clients`, `/clients/new`, `/clients/{id}` — lista com busca, cadastro com
  qualificação completa e ficha com os casos vinculados.
- `ClientPicker` (busca por nome/CPF/código, com cadastro inline) substituiu
  o campo "Token do cliente" em `/cases/new` e na edição do caso.
- `PlatformSelect`/`FraudModalitySelect` (`components/cases/CatalogSelect.tsx`)
  são reutilizados em novo caso, edição, relato inicial e correção da
  triagem — sempre com a opção "Outro (cadastrar)".
- Lista e cabeçalho do caso exibem `CAS-2026-000123 · Nome do Cliente`.
  Nenhum UUID aparece em tela.

## Testes

Backend: `test_documents.py`, `test_identifiers.py` (incluindo concorrência e
rollback), `test_clients_api.py`, `test_catalog_api.py` e `test_cases_api.py`
(transação atômica caso+cliente, isolamento de catálogo cross-tenant, busca
por nome do cliente).

Frontend: `page.test.tsx` das rotas de cliente, do novo caso e da edição.
As fábricas de objetos de domínio ficam em `src/test/factories.ts` — antes
`makeCase` estava duplicado em sete arquivos de teste.
