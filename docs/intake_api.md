# API de Intake e revisão humana (Fase 2.4)

Documentação técnica dos endpoints de `backend/app/api/v1/intake.py`. A
documentação interativa (Swagger/Redoc) continua sendo a fonte
autoritativa em runtime — `GET /docs`, `GET /redoc`, `GET /openapi.json`,
tag `intake` — este arquivo é o complemento narrativo, com as decisões de
design que não cabem numa descrição de rota.

Todas as rotas ficam sob `/api/v1/cases/{case_id}/...`, exigem
`Authorization: Bearer <access_token>` (`TenantMiddleware`) e derivam
`tenant_id`/`user_id` do JWT — nunca do payload (CLAUDE.md, seção 7).

## Endpoints

| Método | Rota | RBAC | Descrição |
|---|---|---|---|
| POST | `/cases/{case_id}/intake` | admin, lawyer, paralegal | Registra o relato inicial (idempotente por caso). |
| GET | `/cases/{case_id}/intake` | qualquer papel autenticado | Consulta o relato inicial. |
| PATCH | `/cases/{case_id}/intake` | admin, lawyer, paralegal | Corrige campos do relato inicial. |
| POST | `/cases/{case_id}/documents` | admin, lawyer, paralegal | Adiciona item ao checklist de documentos. |
| GET | `/cases/{case_id}/documents` | qualquer papel autenticado | Lista o checklist de documentos. |
| PATCH | `/cases/{case_id}/documents/{document_id}` | admin, lawyer, paralegal | Atualiza status/observações de um item. |
| POST | `/cases/{case_id}/intake/run` | admin, lawyer, paralegal | Executa coordinator + triage (orchestrator/graphs/intake.py). |
| GET | `/cases/{case_id}/intake/result` | qualquer papel autenticado | Consulta o resultado mais recente da execução. |
| POST | `/cases/{case_id}/intake/review` | admin, lawyer, paralegal | Registra aprovar/corrigir/devolver. |
| POST | `/cases/{case_id}/intake/advance` | admin, lawyer, paralegal | Conclui a abertura do caso e avança para evidências, sem recomendação de IA. |
| GET | `/cases/{case_id}/audit-log` | admin, lawyer, paralegal (não viewer) | Histórico de auditoria do caso. |

`viewer` só lê (CLAUDE.md, seção 12) — com uma exceção: o histórico de
auditoria é restrito a admin/lawyer/paralegal, por expor metadados técnicos
(nomes de modelo, hashes, ids internos de agente) que não fazem sentido para
um papel somente-leitura.

## Executar o Intake (`POST .../intake/run`)

1. Carrega `Case` + `CaseIntake` (relato) do tenant autenticado.
2. Monta o `CaseState` inicial (ver
   `app/services/intake_orchestration_service.py::_build_initial_state`) e
   invoca `orchestrator.graphs.intake.build_intake_graph()` — coordinator,
   depois triage se o coordinator confirmar o escopo digital (Fase 2.3).
3. Persiste o resultado: `Case` (via `persist_intake_recommendation`),
   checkpoint do `CaseState` (`orchestrator/checkpoints.py`) e cada entrada
   de `audit_trail` em `audit_logs` — tudo numa única transação.

**Provedor de IA ainda não configurado.** `get_llm_client` (dependency
FastAPI) sempre levanta `503 Service Unavailable` — nenhuma implementação
real de `orchestrator.llm.LLMClient` existe neste projeto ainda (sem
credenciais, ver docs/intake_graph_flow.md). O endpoint já está totalmente
funcional e testado via stub (`app.dependency_overrides`); só falta plugar
um client real quando houver um provedor configurado.

| Situação | Status |
|---|---|
| Caso não existe neste tenant | 404 |
| Caso existe, mas sem relato inicial (`CaseIntake`) | 422 |
| Sem provedor de IA configurado | 503 |
| Saída do modelo não valida contra o schema esperado | 502 |
| Sucesso | 200 + `IntakeResultResponse` |

## Consultar o resultado (`GET .../intake/result`)

Combina duas fontes, porque nem tudo tem coluna própria em `cases`:

- **`Case`** (já persistido): `platform`, `fraud_type`, `urgency`, `area`,
  `matter`, `status`, `current_module`, `human_review_required`.
- **Checkpoint mais recente** (`CaseState`, `case_checkpoints`):
  `intake_outcome`, `missing_information`, `out_of_scope_reason`,
  `documents_requested` — só existem no resultado do grafo, nunca em `cases`.

`404` se o Intake nunca rodou para o caso (nenhum checkpoint ainda).

## Revisão humana (`POST .../intake/review`)

Três decisões (`IntakeReviewDecision`):

| Decisão | Efeito no `Case` | `notes` obrigatório? |
|---|---|---|
| `approve` | `human_review_required=False`, `status=in_progress`, `current_module=evidence` | Não |
| `correct` | Aplica os campos corrigidos do payload (`platform`/`fraud_type`/`urgency`/`area`/`matter`), depois o mesmo efeito de `approve` | Sim |
| `return_for_information` | `human_review_required=True`, `status=in_progress`, `current_module` continua `intake` | Sim |

`notes` é a justificativa do advogado — fica em claro no `metadata` da
entrada de auditoria (nunca hasheado, ao contrário de `input_data`/
`output_data`), porque precisa ser visível no histórico do caso
(docs/roadmap_mvp_squad_digital.md, 2.6).

**Pré-condição:** só é possível revisar quando `Case.status ==
PENDING_APPROVAL` — o estado só atingido quando
`intake_outcome == "awaiting_human_review"` (Fase 2.3). Um caso "blocked"
(fora do escopo), "awaiting_information" (dados insuficientes) ou nunca
executado não tem uma recomendação estruturada para aprovar/corrigir: o
caminho correto nesses casos é completar o relato/checklist e chamar
`POST .../intake/run` de novo. Tentar revisar fora dessa janela devolve
`409 Conflict`.

`approve`/`correct` nunca avançam o caso além do módulo `evidence` — nenhuma
estratégia ou peça jurídica é aprovada aqui (CLAUDE.md, seção 2); esses
módulos ainda nem existem.

## Avanço da abertura do caso (`POST .../intake/advance`)

A revisão acima pressupõe que exista uma recomendação de IA a revisar. Como
nenhum provedor de IA está configurado neste ambiente, `POST .../intake/run`
responde `503` e o caso **nunca** chega a `PENDING_APPROVAL` — sem esta rota,
todo caso ficaria preso em `intake` indefinidamente, inclusive para `admin`.

| Aspecto | Comportamento |
|---|---|
| Efeito no `Case` | `current_module=evidence`, `status=in_progress`, `human_review_required=False` |
| `notes` | Opcional — vai em claro no `metadata` da auditoria, como em `review` |
| Pré-condição | `current_module == intake` (senão `409`) e `CaseIntake` já registrado (senão `422`) |
| Auditoria | `actor="human"`, ação `"avanço manual da abertura de caso para evidências"`, com `ai_triage_reviewed=False` |

Não é uma decisão automática nem aprovação de conteúdo jurídico (CLAUDE.md,
seção 2): é o advogado assumindo explicitamente que a abertura está completa.
O `ai_triage_reviewed=False` no metadata deixa registrado no histórico que
nenhuma recomendação de IA foi revisada nesse avanço — quem ler a auditoria
depois não confunde os dois caminhos.

Na interface, `AdvanceStageAction` some quando existe recomendação pendente
(`status == pending_approval`): ali o caminho correto é aprovar/corrigir/
devolver, não avançar por fora da revisão.

## Erros consistentes

Todas as rotas seguem o mesmo padrão do resto da API
(`app/api/v1/cases.py`): `HTTPException` com `detail` em texto simples, sem
stack trace, sem vazar dados de outro tenant — um caso de outro tenant
sempre resulta em `404`, nunca `403` (não confirma nem nega a existência do
recurso para quem não é dono).

## Testes

`backend/tests/test_intake_api.py` (19 testes): autenticação (todas as
rotas exigem token), RBAC (viewer bloqueado nas mutações e no audit-log,
paralegal liberado, viewer liberado nas leituras), isolamento entre tenants
(todas as rotas, incluindo `/intake/run` sob um LLMClient stubado — sem
isso, a falta de provedor mascararia o teste com 503 em vez de 404), e o
fluxo completo de revisão humana (approve/correct/return_for_information,
incluindo os 409 de conflito).
