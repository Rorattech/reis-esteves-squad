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
- **Linha inteira clicável** (`<tr onClick>` → `router.push`), não só a
  coluna Plataforma. A célula Plataforma continua sendo um `<Link>` de
  verdade: é o alvo de navegação por teclado e leitor de tela da linha, que
  um `onClick` no `<tr>` sozinho não oferece.
- **Coluna Ações** (`CaseRowActions`) com ícones `lucide-react` de editar e
  excluir. Todo clique ali chama `e.stopPropagation()` — sem isso, "Excluir"
  abriria o caso por baixo do diálogo de confirmação. Editar leva a
  `/cases/{id}/editar`; excluir passa por `ConfirmDialog` (ação
  irreversível, CLAUDE.md seção 16) e só chama `DELETE /cases/{id}` depois da
  confirmação, recarregando a lista a partir do backend em vez de remover a
  linha de forma otimista.
- Visibilidade das ações por papel: editar para `admin`/`lawyer`/`paralegal`,
  excluir só para `admin`/`lawyer` (espelha `_require_case_deleter`). É
  conveniência de UX — o backend reforça a autorização de verdade.

### `src/app/(app)/cases/new/page.tsx` — Novo Caso (rota nova)

Formulário com `react-hook-form` + `zod`, mesmo padrão de
`src/app/login/page.tsx`. Campos, espelhando `CaseCreate`
(`backend/app/models/schemas/case.py`):

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `platform` | texto (≤100) | sim | |
| `fraud_type` | select | sim | |
| `urgency` | select | não (default "medium") | |
| `client_id` — "Token do cliente" | texto | não | validado como UUID no formulário; a existência do cliente **neste tenant** só o backend confirma (`404 Cliente não encontrado.`) |
| `area` — "Área" | select | não | opção em branco = "A definir na triagem" |
| `matter` — "Matéria" | texto (≤255) | não | |

Campos opcionais em branco são **omitidos do payload** em vez de enviados
como `""` — o backend rejeitaria com 422 (`client_id` espera UUID, `area`
espera um valor do enum `CaseArea`).

Validação no frontend é só a primeira camada — o backend continua
validando e a mensagem de erro da API (`ApiError.message`, já preparado
para o formato `detail` de erro 422 do FastAPI) é exibida se passar da
validação do formulário mas falhar no servidor. Sucesso redireciona para
`/cases/{id}` via `router.push`.

### `src/app/(app)/cases/[caseId]/editar/page.tsx` — Editar caso (rota nova)

Mantém token do cliente, área e matéria **visíveis e editáveis depois da
criação**, via `PATCH /cases/{id}`. Mesmos campos e validações do formulário
de Novo Caso, com uma diferença: token do cliente em branco vira `null`
explícito (desvincula o cliente), não é omitido.

Só edita dados de cadastro. `status` e `current_module` não aparecem aqui:
são definidos pelo backend a partir das decisões de revisão humana do fluxo
(CLAUDE.md, seção 16 — a interface nunca simula avanço de etapa).

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

- **Token do cliente é digitado, não escolhido em um seletor.** `client_id`
  agora é preenchível no formulário (Novo Caso e Editar caso), mas como
  texto: continua não existindo nenhum endpoint `GET/POST /clients` (a Fase
  2.1 criou `client_service.py`, nunca uma rota — ver
  docs/phase_2_intake_domain.md). Um `<select>` de clientes exigiria uma
  tela e um endpoint que não existem; o campo de token usa o que o backend
  de fato aceita hoje, com o formato validado no formulário e a existência
  validada pelo servidor.
- **`area`/`matter` são opcionais, e é de propósito.** Continuam sendo o
  produto esperado da triagem (Fase 2.3 — nó `triage`); o formulário os
  oferece para o caso em que o advogado já sabe a classificação, sem nunca
  exigi-los. A opção em branco de Área é rotulada "A definir na triagem"
  justamente para não sugerir que o preenchimento humano substitui a
  triagem.

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

### Cobertura acrescentada com a linha clicável, as ações e a edição

`cases/page.test.tsx`: navegação ao clicar numa célula que não é link nem
botão (prova que a linha inteira responde); clique em Editar e em Excluir
**não** dispara a navegação da linha (`stopPropagation`); exclusão só após
confirmação, com recarga da lista pelo backend; cancelamento sem chamar a
API; erro de API exibido sem tirar o caso da lista; e visibilidade das ações
por papel (paralegal edita mas não exclui; viewer não vê nenhuma).

`[caseId]/editar/page.test.tsx`: carregamento, campos pré-preenchidos, salvar,
desvincular cliente (token apagado → `null`), token em formato inválido sem
chamar a API, erro do backend sem redirecionar, e acesso negado para viewer.

`[caseId]/intake/page.test.tsx`: avanço da abertura para Evidências com
confirmação e recarga pelo backend; bloqueio sem relato inicial; erro do
backend sem marcar o caso como avançado; e as três situações em que a ação
não deve aparecer (recomendação pendente, papel viewer, caso já em
Evidências).

### Nota sobre a configuração do Vitest

`@testing-library/react` só limpa o DOM entre testes automaticamente via um
`afterEach` **global** — como o projeto roda com `globals: false` (imports
explícitos de `describe`/`it`/`expect`, sem globais ambientes, para bater
com o resto do código que sempre importa tudo explicitamente), isso nunca
acontecia sozinho. `vitest.setup.ts` registra `afterEach(cleanup)`
manualmente — sem isso, o DOM de um teste vazava para o próximo
(elementos duplicados, mocks de estado obsoletos).

---

## Navegação de etapas (revisão de usabilidade)

A primeira versão desta fatia comunicava a etapa do caso apenas por destaque
de cor na linha do tempo, e a única forma de descobrir **como** passar de
fase era entrar na aba certa e encontrar o formulário lá dentro. Depois de
criar um caso o advogado caía na Visão geral — uma tabela de dados, sem
nenhuma ação — com as abas seguintes bloqueadas e nenhuma explicação: a
sensação relatada foi de caso "travado". O fluxo do backend estava completo
(`POST .../intake/review` e `POST .../intake/advance`); o que faltava era
interface.

Nada disso mudou quem decide a etapa: `Case.current_module` continua sendo
definido só pelo backend, e a interface segue não simulando avanço
(CLAUDE.md, seção 16).

### `src/lib/caseStages.ts` — orientação derivada do estado do backend

- `stageProgress(currentModule, stage)` → `"done" | "current" | "locked"`,
  com `STAGE_PROGRESS_LABELS` para nomear a situação em texto (não só em
  cor). Um teste garante a coerência com `isStageUnlocked`: só etapa
  `locked` deixa de ser navegável.
- `stageNumber` / `stageForSegment` / `stageFor` — posição no workflow e
  tradução rota ⇄ etapa em um único lugar.
- `stageGuidance(caseData)` — a partir de `current_module` + `status`,
  devolve onde o caso está (`"Etapa 2 de 6 · Evidências"`), o que fazer
  agora, o rótulo do botão e `notImplementedYet`. Os textos distinguem os
  dois caminhos reais de saída da abertura: revisar a recomendação da
  triagem (`status === "pending_approval"`) ou concluir a abertura
  manualmente quando não há recomendação a revisar.

### `CaseTimeline.tsx` — stepper explícito

Cada etapa passou a mostrar número (ou ✓ concluída / 🔒 bloqueada), nome e a
situação escrita embaixo. A aba aberta é marcada por contorno, separando os
dois sinais que antes se confundiam: **cor = progresso do caso**, **contorno
= aba que você está vendo**. Abaixo do stepper, uma linha diz em que etapa o
caso está e que as seguintes destravam pelo backend.

O número fica em um `<span aria-hidden>` **irmão** do link/label, não filho:
o nome acessível de cada etapa continua sendo exatamente o label
(`getByRole("link", { name: "Evidências" })`), e a etapa bloqueada continua
sendo um `<span aria-disabled="true">` cujo texto é só o label.

### `CaseStageGuide.tsx` (novo) — "o que fazer agora"

Cartão fixo no layout do caso, acima do conteúdo da aba: posição no
workflow, ação de avanço e botão para a aba onde a ação existe. O botão é
omitido (`showCta={false}`) quando o advogado já está na aba da etapa atual —
lá a ação está no próprio conteúdo. Para as etapas sem interface (Pesquisa,
Estratégia, Minuta, Revisão) o texto diz que o módulo não existe ainda, em
vez de prometer trabalho a fazer.

### `CaseStageLockedNotice.tsx` (novo) — etapa bloqueada por URL

A linha do tempo não linka etapas futuras, mas a URL sempre continuou
acessível (link salvo, botão voltar, digitação) e abria a vitrine vazia do
`ModulePlaceholder`, que soa como "módulo não existe" em vez de "etapa ainda
não liberada". O layout agora detecta segmento de etapa bloqueada e mostra o
motivo + botão para a etapa atual, no lugar do conteúdo da aba.

### Aba Abertura de caso e lista

- `intake/page.tsx`: seções numeradas (Passo 1 relato → Passo 2 triagem,
  opcional → Passo 3 revisão humana), com o passo 3 dizendo explicitamente
  que é ali que o caso passa de fase.
- `AdvanceStageAction.tsx`: com recomendação pendente o card não desaparece
  mais sem explicação — passa a apontar que o caminho é aprovar/corrigir a
  triagem acima (pendência de revisão nunca fica escondida).
- `cases/page.tsx`: a coluna "Etapa atual" mostra `2/6 · Evidências`, dando
  a posição no workflow sem abrir o caso.

### Cobertura de teste

`src/lib/caseStages.test.ts` (novo, 9 casos): classificação de etapas,
coerência com `isStageUnlocked`, numeração, resolução de segmento e os
textos de orientação por estado (abertura sem recomendação, recomendação
pendente, evidências, etapa não implementada, caso arquivado).

`src/components/cases/CaseStageGuide.test.tsx` (novo, 5 casos): posição,
ação e href por etapa/status; ausência do botão na aba da própria etapa;
etapa não implementada.

`[caseId]/layout.test.tsx`: situação de cada etapa nomeada em texto
(1 concluída / 1 atual / 4 bloqueadas), orientação com link quando se está
em outra aba, ausência do botão na aba da etapa atual, e etapa bloqueada
aberta por URL direta (conteúdo da aba não renderizado).

### Nota de ambiente

`jsdom@30` depende de `undici@8`, que exige Node `>=22.19.0`; o ambiente de
desenvolvimento usado aqui roda Node 20.20.1, onde `npx vitest run` falha no
startup (`webidl.util.markAsUncloneable is not a function`) antes de executar
qualquer teste. A suíte desta revisão foi rodada em Node 22 via container
(`node:22-bookworm-slim`) — 87 testes, todos passando, mais `tsc --noEmit` e
`eslint src --max-warnings=0` limpos. Vale alinhar a versão de Node do
projeto (`.nvmrc`/engines) numa próxima passada.
