# ADR 0004 — Identificadores legíveis, qualificação do cliente e catálogos de classificação

- **Status:** aceito
- **Data:** 2026-08-07
- **Fase:** 2.7 (retrabalho da abertura de caso, antes da Fase 4)

## Contexto

A abertura de caso obrigava o advogado a **colar um UUID à mão** no campo
"Token do cliente" (`frontend/src/app/(app)/cases/new/page.tsx`), e a lista de
casos exibia esse mesmo UUID na coluna "Cliente". O modelo `Client` existia
desde a migration `41280d8b096c`, com serviço e schemas prontos e auditados,
mas **sem nenhuma rota HTTP e sem nenhuma tela** — não havia como cadastrar um
cliente pelo produto.

Três problemas se somavam:

1. **UUID como identidade visível.** O caso não tinha outro identificador. Um
   advogado não cita "3f2a9c10-4b7e-4d51-9a2f-8e0c1d6b5a44" ao telefone.
2. **Vocabulário invertido.** `cases.platform` era texto livre de 100
   caracteres (então "WhatsApp", "whatsapp" e "Whats" eram três plataformas),
   enquanto a modalidade era um enum fechado de cinco valores (então o
   escritório não cadastrava um golpe novo sem deploy).
3. **Prompts pedindo dado inexistente.** `prompts/digital/evidence/specialist.md`
   pedia `FORO RECOMENDADO` — que depende do domicílio do consumidor
   (CDC art. 101, I) — e ambos os prompts abriam com `Processo: [Cliente / Matéria]`.
   Nem comarca nem identificação do caso chegavam ao grafo: `_build_initial_state`
   nunca lia `case.client_id`.

## Decisão

### 1. Duas identidades por entidade, com papéis distintos

O UUID continua sendo chave primária e o que aparece na URL — não é enumerável.
Ao lado dele, um **código legível emitido por escritório**:

| Série | Formato | Reinicia por ano |
|---|---|---|
| Caso | `CAS-2026-000123` | sim |
| Cliente | `CLI-000042` | não (o cliente atravessa anos) |

A emissão vive em `backend/app/core/identifiers.py`. Uma `SEQUENCE` do Postgres
é global ao banco e faria o primeiro caso do segundo escritório nascer como
`CAS-2026-000008`; a contagem por tenant fica em `tenant_counters`, alocada em
uma única instrução `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, cujo row
lock serializa requests concorrentes sem transação explícita.

O ano vem de `America/Sao_Paulo`, não de UTC: um caso aberto em 31/dez às 21h
receberia o código do ano seguinte.

Buracos na sequência são aceitáveis — o código identifica, não conta casos.

**Alternativa rejeitada:** código derivado do documento (`CLI-52998224725`).
Legível e auto-vinculado, mas colocaria CPF em URL, tela e histórico de
auditoria, contra CLAUDE.md seção 12.

### 2. CPF/CNPJ é chave de vinculação interna, nunca credencial

O documento é o que deduplica cliente dentro do escritório
(`uq_clients_tenant_id_document_number`, sempre normalizado para só dígitos por
`app/core/documents.py`). Ele **não** é, e não pode virar, um fator de
autenticação: CPF no Brasil é dado amplamente vazado, então um portal futuro
que liberasse o dossiê a quem "informar o CPF" seria um incidente de LGPD, não
uma funcionalidade. Autenticação de cliente exigirá posse verificada (OTP no
telefone/e-mail cadastrado) ou token por caso emitido pelo advogado.

Vale a distinção que costuma confundir: mesmo quando o **processo judicial** é
público (CPC art. 189), o **dossiê dentro deste sistema** — evidências,
estratégia, minuta — é coberto por sigilo profissional (EOAB art. 34, VII) e
não é público em nenhuma hipótese.

### 3. Catálogos por tenant, com famílias fechadas por baixo

`platforms` e `fraud_modalities` são tabelas com `tenant_id NOT NULL` + RLS,
semeadas a partir de `app/core/catalog_defaults.py`. O escritório cadastra
entradas próprias pela opção "Outro".

O ponto que faz isso funcionar: **cada modalidade declara uma `family`** do enum
`FraudType` existente. O advogado cadastra "golpe da falsa central de
atendimento" e diz que aquilo é da família `pix`; o grafo e os prompts continuam
raciocinando sobre as cinco famílias que conhecem. Vocabulário aberto para o
usuário, fechado para os agentes.

`cases.platform` (texto) e `cases.fraud_type` (enum) **permanecem**, agora como
rótulo e família **denormalizados** da entrada escolhida. É o que manteve
`orchestrator/`, os prompts e as migrations de seed lendo os mesmos campos de
sempre. Eles nunca são escritos direto.

**Alternativa rejeitada:** catálogo global com `tenant_id` nulo. Exigiria uma
policy de RLS diferente de todas as outras tabelas (`tenant_id IS NULL OR
tenant_id = ...`), e CLAUDE.md seção 7 é explícito: toda nova tabela tem
`tenant_id UUID NOT NULL` com política RLS. Semear ~26 linhas por escritório é
barato e mantém uma regra só.

**Semear sob demanda, não no `/register`:** aquela rota usa
`get_auth_bootstrap_session`, cujo bypass de RLS é restrito a `tenants`/`users`.
`ensure_catalog_seeded` roda nas rotas de listagem, na sessão já escopada por
tenant, e reconcilia **por slug** — então uma entrada nova em
`catalog_defaults.py` chega aos escritórios antigos sem migration.

### 4. A triagem deixa de sobrescrever a classificação

`orchestrator/graphs/intake.py::persist_intake_recommendation` **não escreve
mais** `case.platform`/`case.fraud_type`. A leitura do agente permanece no
`CaseState` e é exibida como recomendação; ela só vira classificação do caso
quando um humano corrige explicitamente (`IntakeReviewDecision.CORRECT`, que
agora recebe `platform_id`/`fraud_modality_id`).

Isso não é só consequência do catálogo — é o modelo exigido por CLAUDE.md seção
2. O agente não escolhe entrada de catálogo; ele recomenda, o humano decide.

Por isso `IntakeResultResponse` passou a ler `platform`/`fraud_type` do state, e
não do caso: lê-los do caso mostraria de volta a escolha do próprio advogado
como se fosse recomendação do sistema.

### 5. Só a comarca vai para o modelo

`CaseState` ganhou `case_code`, `client_city` e `client_state`. Nada além disso:
nome, CPF, RG e endereço completo não entram no estado nem trafegam para a IA.
A cidade/UF entra porque fixa o foro do consumidor, que o `specialist` precisa
recomendar; o código do caso entra porque o cabeçalho do relatório precisa
identificar o processo sem citar uma pessoa.

## Versões anteriores dos prompts (CLAUDE.md, seção 11)

| Arquivo | Antes | Depois | Mudança |
|---|---|---|---|
| `prompts/_shared/output_format.md` | 1.0.0 | 1.1.0 | `Processo: [Cliente / Matéria]` → `[Código do caso / Matéria]`; nova seção "Identificação do processo — regra de privacidade" |
| `prompts/digital/evidence/documental.md` | 1.0.0 | 1.1.0 | `case_code` nos Inputs; cabeçalho passa a usar o código; declaração explícita de que não recebe dado pessoal |
| `prompts/digital/evidence/specialist.md` | 1.0.0 | 1.1.0 | `case_code` e `client_city`/`client_state` nos Inputs; `FORO RECOMENDADO` ancorado na comarca com saída "PENDENTE" quando ausente; `QUALIFICAÇÃO DO RÉU` exige fonte verificável |

O conteúdo integral das versões 1.0.0 está no histórico do git (último commit
antes desta ADR: `ace8c35`).

## Consequências

- Abrir um caso passa a exigir uma entrada de catálogo para plataforma e
  modalidade. `CaseCreate` mudou de forma incompatível (`platform`+`fraud_type`
  → `platform_id`+`fraud_modality_id`); não há consumidor externo da API hoje.
- `CaseResponse` ganhou `code`, `client`, `platform_entry` e `fraud_modality`.
  As rotas que a devolvem precisam de eager load (`CASE_RESPONSE_RELATIONSHIPS`
  em `app/api/v1/cases.py`) — sem ele, o Pydantic dispara lazy load em contexto
  async e estoura `MissingGreenlet`.
- `client_service` deixou de fazer `commit()`: a transação pertence à rota. É o
  que permite cadastrar cliente e abrir caso atomicamente, sem cliente órfão
  quando a abertura falha.
- A busca de casos e clientes foi para o servidor: filtrar por nome de cliente
  no navegador exigiria mandar a base inteira, com os nomes, para toda sessão
  aberta. E virou `POST .../search`, não `GET ?search=`: verificando o fluxo no
  navegador, o CPF apareceu em claro no access log do uvicorn
  (`GET /api/v1/clients?search=529.982.247-25`), contra CLAUDE.md seção 12.
  Query string vaza também para histórico de navegador, cabeçalho Referer e
  cache de proxy — o corpo não. Os `GET` continuam para listagem sem termo.
- O acompanhamento pós-protocolo (número CNJ, DataJud, ADVBOX) segue **fora de
  escopo** e não foi decidido aqui.
