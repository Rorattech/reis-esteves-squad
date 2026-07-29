# Fase 2.5 — Lista de casos, novo caso e detalhe

Documentação técnica da fatia frontend da Fase 2 (ver
`docs/roadmap_mvp_squad_digital.md`, seção 2.5).

## Antes de editar

`docs/frontend_foundation_audit.md` (referenciado pelo prompt desta fase)
não existe no repositório — a fundação do frontend (F0) já estava
implementada e commitada (login, layout autenticado, `useAuth`, `api.ts`,
Zustand, componentes de estado em `src/components/ui/`), mas o relatório de
auditoria em si nunca foi salvo. Em vez de recriá-lo retroativamente (fora
do escopo desta fase), inspecionei a fundação existente diretamente no
código-fonte antes de editar, como pedido.

Achado mais importante da inspeção: `src/types/api.ts` estava desatualizado
em relação ao backend real — `Case`/`CaseCreateInput` não tinham
`client_id`, `area`, `matter`, `current_module`, `human_review_required`,
todos adicionados ao `CaseResponse`/`CaseCreate` na Fase 2.1
(`backend/app/models/schemas/case.py`). Corrigido nesta fase.

## O que já existia (F0, reaproveitado sem alteração de arquitetura)

- `src/services/api.ts` — cliente HTTP central, com refresh automático de
  token. `api.listCases`/`api.getCase`/`api.createCase` já existiam e
  continuam sendo os únicos pontos de chamada à API de casos.
- `src/hooks/useCases.ts`/`useCase.ts` — hooks de carregamento.
- `src/hooks/useAuth.ts` + `src/stores/authStore.ts` — sessão.
- `src/components/ui/{EmptyState,ErrorState,LoadingState,StatusBadge,HumanReviewNotice,ConfirmDialog}.tsx`.
- `src/app/(app)/cases/[caseId]/{evidencias,pesquisa,estrategia,minuta,revisao,intake,historico}/page.tsx`
  — todos `ModulePlaceholder` (backend desses módulos não existe, ou — no
  caso de `intake` — a tela ainda não foi feita; isso é a Fase 2.6, fora do
  escopo daqui). Não alterados.

## O que foi implementado/corrigido nesta fase

### `src/types/api.ts` e `src/lib/caseLabels.ts`

`Case` e `CaseCreateInput` atualizados para espelhar `CaseResponse`/
`CaseCreate` reais. Novos tipos `CaseArea` e `ModuleName` (espelham
`app/models/enums.py`). `CASE_AREA_LABELS`/`CASE_STATUS_LABELS` adicionados;
`StatusBadge` passou a importar `CASE_STATUS_LABELS` de `caseLabels.ts` em
vez de duplicar o mapa localmente.

### `src/lib/caseStages.ts` (novo)

`CASE_STAGES`: as 6 etapas do workflow (Intake → Evidências → Pesquisa →
Estratégia → Minuta → Revisão), na ordem fixa de
`orchestrator/router.py::MODULE_ORDER`, com o segmento de rota e o label de
cada uma. `isStageUnlocked(currentModule, stage)`: uma etapa está liberada
se seu índice for `<=` o índice de `Case.current_module` — nunca simula
avanço de etapa por conta própria (CLAUDE.md, seção 16).

### `src/components/cases/CaseTimeline.tsx` (novo)

Linha do tempo visual das 6 etapas. Etapas liberadas são links; etapas
bloqueadas são um `<span aria-disabled="true">` com ícone de cadeado e
`title` explicando o motivo — nunca um link morto ou escondido (o advogado
precisa ver que a etapa existe e que ainda não está disponível).

### `src/components/ui/AccessDeniedState.tsx` (novo)

Estado dedicado para "acesso negado". O backend devolve **404** (nunca 403)
tanto para um caso inexistente quanto para um caso de outro tenant, de
propósito (CLAUDE.md, seção 7 — não confirma nem nega existência para quem
não é dono). Este componente espelha essa ambiguidade: nunca diz "esse caso
existe mas não é seu", só que o acesso não é possível, com um link de volta
para a lista.

### `src/hooks/useCase.ts`

Ganhou o campo `notFound: boolean` (`true` quando `ApiError.status === 404`)
— páginas usam isso para mostrar `AccessDeniedState` em vez do
`ErrorState` genérico (que tem um botão "Tentar novamente" sem sentido para
um 404 permanente).

### `src/app/(app)/cases/page.tsx` — Lista de Casos

- Coluna **Cliente** (`client_id` ou "—" — não há endpoint de cliente ainda,
  ver "Decisões de escopo" abaixo), **Etapa atual** (via `caseStages`), e
  **Última atualização** trocou de `created_at` para `updated_at` (o texto
  pedido pela fase).
- Botão **Novo caso** no cabeçalho e na ação do estado vazio — visível só
  para `admin`/`lawyer`/`paralegal` (mesmos papéis que `POST /cases` aceita,
  `backend/app/api/v1/cases.py::_require_case_writer`). Um `viewer` nunca vê
  o botão; se acessasse a rota diretamente, o backend ainda rejeitaria com
  403 — a UI só evita oferecer uma ação que vai falhar.
- Busca (texto livre sobre plataforma/matéria) e filtro por status — **só
  client-side**, sobre a lista já carregada por `GET /cases`. O endpoint não
  aceita nenhum parâmetro de busca/filtro hoje
  (`backend/app/api/v1/cases.py::list_cases`), então nada aqui finge uma
  capacidade de busca no servidor que não existe.
- Estados: carregando, erro (com "Tentar novamente"), vazio, sucesso — vazio
  tem ação "Criar caso"; nenhum "acesso negado" aqui porque listar o
  próprio tenant nunca falha com 404/403 para um usuário autenticado.

### `src/app/(app)/cases/new/page.tsx` — Novo Caso (rota nova)

Formulário com `react-hook-form` + `zod`, mesmo padrão de
`src/app/login/page.tsx`. Campos: `platform` (texto, obrigatório, ≤100
caracteres), `fraud_type` (select, obrigatório), `urgency` (select, default
"medium") — exatamente os campos de `CaseCreate`
(`backend/app/models/schemas/case.py`) que fazem sentido pedir na abertura
do caso. Validação no frontend é só a primeira camada — o backend continua
validando e a mensagem de erro da API (`ApiError.message`, já preparado
para o formato `detail` de erro 422 do FastAPI) é exibida se passar da
validação do formulário mas falhar no servidor. Sucesso redireciona para
`/cases/{id}` via `router.push`.

### `src/app/(app)/cases/[caseId]/layout.tsx` — Detalhe do Caso

A navegação por abas virou duas coisas distintas:

1. `CaseTimeline` — as 6 etapas do pipeline, com bloqueio.
2. Duas abas "de metadado" que não são etapas do pipeline: **Visão geral** e
   **Histórico** — sempre acessíveis, sem bloqueio (não fazem parte da
   sequência que `current_module` governa).

`AccessDeniedState` substitui o `ErrorState` genérico quando
`useCase(...).notFound` é `true`.

### `src/app/(app)/cases/[caseId]/page.tsx` — Visão geral

Ganhou os campos **Cliente**, **Etapa atual**, **Área** e **Matéria**
(todos presentes em `CaseResponse` desde a Fase 2.1, mas nunca exibidos).
Mesma lógica de `notFound` → `AccessDeniedState`.

## Decisões de escopo (o que ficou de fora, de propósito)

- **Sem seletor de cliente no formulário de Novo Caso.** `CaseCreate`
  aceita `client_id` opcional, mas não existe nenhum endpoint
  `GET/POST /clients` (Fase 2.1 criou `client_service.py`, mas nunca uma
  rota — ver docs/phase_2_intake_domain.md). Adicionar um seletor de
  cliente exigiria inventar uma tela/endpoint que não existe. `client_id`
  continua no tipo `CaseCreateInput` (é real no backend), só não é
  preenchido por este formulário.
- **Sem `area`/`matter` no formulário de Novo Caso.** Esses campos são o
  produto da triagem (Fase 2.3 — nó `triage`), não algo que o advogado
  digita ao abrir o caso. Pedi-los aqui antecipa uma decisão que é do
  copiloto, não do formulário de abertura.
- **Aba "Intake" continua `ModulePlaceholder`.** O backend de intake existe
  desde a Fase 2.4, mas a tela (relato inicial, checklist, executar
  triagem, revisão humana) é a Fase 2.6 — um passo seguinte do roadmap,
  não desta fase.

## Testes

Nenhum framework de teste de frontend existia. Adicionado **Vitest +
Testing Library** (`package.json`, `vitest.config.ts`, `vitest.setup.ts`) —
runtime Node/jsdom, sem depender de um browser real nem do backend rodando;
todas as chamadas de API são mockadas via `vi.mock("@/services/api", ...)`.

`npm test` roda `vitest run`. 11 testes em 3 arquivos, cobrindo os 6
cenários pedidos:

| Cenário pedido | Teste |
|---|---|
| Usuário autenticado consultando casos | `cases/page.test.tsx` → "lista os casos do tenant autenticado" |
| Estado vazio | `cases/page.test.tsx` → "mostra o estado vazio com ação de criar caso" |
| Falha de API | `cases/page.test.tsx` → "mostra erro com opção de tentar novamente"; `[caseId]/layout.test.tsx` → "erro genérico" |
| Criação com validação inválida | `cases/new/page.test.tsx` → "mostra erros de validação e não chama a API" |
| Criação bem-sucedida | `cases/new/page.test.tsx` → "cria o caso e redireciona para o detalhe" |
| Acesso a um caso indisponível | `[caseId]/layout.test.tsx` → "mostra acesso negado" |

Testes extras (não pedidos explicitamente, mas cobrem regras do CLAUDE.md
exercitadas nesta fase): RBAC do botão "Novo caso" por papel, filtro/busca
client-side sem nova chamada à API, e bloqueio de etapas futuras na linha
do tempo.

### Nota sobre a configuração do Vitest

`@testing-library/react` só limpa o DOM entre testes automaticamente via um
`afterEach` **global** — como o projeto roda com `globals: false` (imports
explícitos de `describe`/`it`/`expect`, sem globais ambientes, para bater
com o resto do código que sempre importa tudo explicitamente), isso nunca
acontecia sozinho. `vitest.setup.ts` registra `afterEach(cleanup)`
manualmente — sem isso, o DOM de um teste vazava para o próximo
(elementos duplicados, mocks de estado obsoletos).
