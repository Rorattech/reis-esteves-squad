# Fase 2.6 — Formulário de intake e revisão da triagem

Documentação técnica da aba Intake (ver `docs/roadmap_mvp_squad_digital.md`,
seção 2.6) — onde o humano no loop passa a existir de verdade: relato →
triagem → resultado → aprovar/corrigir/devolver.

## Antes de editar

Reinspecionei os schemas e rotas reais da Fase 2.4
(`backend/app/models/schemas/{case_intake,case_document,intake}.py`,
`backend/app/api/v1/intake.py`) em vez de assumir os campos do prompt desta
fase. Dois achados mudaram o design:

1. **`IntakeResultResponse` não expõe "fatos extraídos"/resumo do caso.**
   `TriageRecommendation.case_summary` (o resumo que o LLM produz) só existe
   hasheado dentro de `output_data` da entrada de auditoria
   (`orchestrator/graphs/intake.py::triage` → `create_audit_entry`) — nunca
   em texto plano em nenhum endpoint. Em vez de inventar um campo, o painel
   de resultado mostra o que a API realmente devolve (plataforma, modalidade,
   urgência, área, matéria, pendências, checklist) e omite uma seção de
   "fatos extraídos". Expor `case_summary` de verdade exigiria mudar o
   backend (fora do escopo de uma tarefa só de frontend) — registrado aqui
   para uma fase futura.
2. **"Próximo módulo recomendado" não é um campo literal.** É inferido de
   `intake_outcome === "awaiting_human_review"` — o único caso em que
   `review_intake_recommendation` (Fase 2.4) avança `current_module` para
   `"evidence"` ao aprovar/corrigir. A UI nunca inventa um destino diferente
   do que o backend realmente faz.

`estimated_loss_amount` chega como **string** no JSON (`Decimal` serializado
pelo Pydantic) — confirmado empiricamente, não assumido; `types/api.ts`
documenta isso.

## Arquivos novos

### Tipos e serviço (`src/types/api.ts`, `src/services/api.ts`)

Tipos novos espelhando 1:1 os schemas Pydantic: `CaseIntake(CreateInput)`,
`CaseDocument(CreateInput/UpdateInput)`, `IntakeResult`, `IntakeReviewInput`,
`AuditLogEntry`, mais `CaseUpdateInput` (faltava — `PATCH /cases/{id}` já
existia desde a Fase 2.1 mas o frontend nunca o chamava). `api.ts` ganhou um
método por endpoint de `app/api/v1/intake.py`: `getCaseIntake`,
`submitCaseIntake`, `updateCaseIntake`, `listCaseDocuments`,
`addCaseDocument`, `updateCaseDocument`, `runIntake`, `getIntakeResult`,
`reviewIntake`, `getAuditLog`.

### Hooks (`src/hooks/`)

`useCaseIntake`, `useCaseDocuments`, `useIntakeResult`, `useAuditLog` — mesmo
padrão de `useCase`/`useCases` (Fase 2.5): `isLoading`/`error`/`reload`, mais
uma flag específica por hook para distinguir "404 esperado" de erro real
(`notSubmittedYet`, `notRunYet`, `forbidden`) — o mesmo princípio de
`useCase.notFound`.

### `src/lib/roles.ts` (novo)

`canWriteCase(user)` — extraído de `cases/page.tsx` (Fase 2.5), agora
reutilizado em toda a aba Intake. Mesmo conjunto de papéis
(`admin`/`lawyer`/`paralegal`) que `_require_case_writer` aceita em
`backend/app/api/v1/{cases,intake}.py`.

### Componentes (`src/components/cases/`)

- **`IntakeNarrativeForm`** — relato inicial. Salva em dois passos reais:
  `PATCH /cases/{id}` (plataforma/modalidade/urgência — já existiam desde a
  abertura do caso) e `POST /cases/{id}/intake` (o resto — narrativa, valor
  envolvido, data do ocorrido, BO, documentos disponíveis, informações
  desconhecidas). `claimed_documents`/`pending_information` (listas no
  schema real) viram textarea de uma linha por item — não há campo de lista
  dinâmica dedicado, e isso evita a complexidade de um `useFieldArray` para
  uma lista de strings simples. `has_police_report` (booleano opcional) vira
  três rádios Sim/Não/Não sei, porque o schema aceita `null` — "não sei" é
  um valor real, não um "não preenchido".
- **`RunTriageAction`** — botão "Executar triagem": desabilitado sem relato
  (`hasIntake`), `ConfirmDialog` antes de chamar `POST .../intake/run`,
  desabilitado durante a chamada (bloqueio de clique duplicado), erro visível
  sem fingir sucesso.
- **`IntakeResultPanel`** — escopo (via `intake_outcome`), plataforma/
  modalidade/urgência prováveis, área/matéria, pendências (nunca ocultadas),
  aviso de fora de escopo quando `blocked`, `HumanReviewNotice` fixo, e o
  checklist (`CaseDocumentChecklist`) embutido.
- **`CaseDocumentChecklist`** — o checklist estruturado real
  (`GET/POST/PATCH .../documents`), distinto de `claimed_documents` (o que o
  cliente *diz* ter, sem status). Mostra `documents_requested` da triagem
  como sugestões com um botão "Adicionar ao checklist" — a sugestão nunca
  vira uma linha de `CaseDocument` sozinha, só quando o advogado confirma.
- **`IntakeReviewForm`** — Aprovar (confirmação direta) / Corrigir /
  Devolver para complementação (ambos revelam um formulário com `notes`
  obrigatório, mesma regra de `IntakeReviewRequest.notes` no backend).
  "Corrigir" expõe os únicos campos que `IntakeReviewRequest` aceita mudar
  (`platform`/`fraud_type`/`urgency`/`area`/`matter`), pré-preenchidos com o
  resultado da triagem. **Só aparece quando `case.status === "pending_approval"`**
  — o único estado em que o backend aceita a revisão (fora dele, 409); nos
  demais estados mostra uma mensagem neutra em vez de botões que vão falhar.
- **`AuditLogTimeline`** — histórico de auditoria (`GET .../audit-log`),
  reutilizado em dois lugares: resumido (últimas 5) dentro da aba Intake, e
  completo na aba **Histórico** (`cases/[caseId]/historico/page.tsx`, que
  era `ModulePlaceholder` e passou a usar este componente — "toda revisão
  deve ser visível no histórico do caso" é literal, não só dentro da aba
  Intake).

### Página (`src/app/(app)/cases/[caseId]/intake/page.tsx`)

Orquestra os hooks acima e recarrega **tudo** (`caso`, `relato`, `resultado`,
`checklist`, `histórico`) depois de qualquer ação — nunca atualização
otimista: a classificação e a decisão de avançar são sempre do backend.

## Regras do enunciado, e como foram cumpridas

| Regra | Onde |
|---|---|
| Não chamar "aprovação" sem o backend aceitar | `IntakeReviewForm` só mostra os botões quando `status === "pending_approval"`; erros de `409`/outros da API aparecem como texto, nunca como sucesso simulado. |
| Não ocultar pendências da triagem | `IntakeResultPanel` sempre renderiza `missing_information` (mesmo vazio, com texto explícito) e o aviso de fora de escopo. |
| Não apresentar classificação como fato definitivo | Labels "provável"/"recomendado", `HumanReviewNotice` fixo, texto explicativo no `IntakeReviewForm`. |
| Toda revisão visível no histórico do caso | `AuditLogTimeline` (aba Intake resumida + aba Histórico completa), alimentado por `GET .../audit-log` — a mesma linha que `review_intake_recommendation` grava. |

## Testes

`src/app/(app)/cases/[caseId]/intake/page.test.tsx` — 12 testes cobrindo os
5 cenários pedidos (aprovação, correção, devolução, falha, carregamento),
mais os obrigatórios da ação de triagem (bloqueio sem relato, confirmação,
bloqueio de clique duplo) e da revisão (gate por status, validação de
justificativa obrigatória, payload exato enviado ao backend). Suíte
completa do frontend: **23 testes em 4 arquivos**, `tsc --noEmit` e
`next build` limpos.
