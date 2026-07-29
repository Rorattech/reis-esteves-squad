# Fluxo do módulo Intake — nós `coordinator` e `triage`

Documentação técnica da Fase 2.3 (ver `docs/roadmap_mvp_squad_digital.md`).
Implementa os dois primeiros agentes do Squad Digital
(`prompts/digital/intake/coordinator.md` e `.../triage.md`) como nós
LangGraph em `orchestrator/graphs/intake.py`.

## Grafo

```
START → bootstrap_case → coordinator ─┬─(intake_outcome == "completed")─→ triage → END
                                       └─(blocked | awaiting_information)──────────→ END
```

- **`bootstrap_case`** (já existia): valida os campos mínimos do `CaseState`
  (`case_id`, `tenant_id`, `platform`, `fraud_type`), sem chamar IA.
- **`coordinator`**: identifica se o relato é do Squad Digital e classifica
  plataforma/modalidade/urgência preliminar.
- **`triage`**: só roda se o coordinator concluiu (`intake_outcome ==
  "completed"`). Normaliza área/matéria/urgência, monta o checklist de
  documentos faltantes e sinaliza o próximo módulo — como recomendação.

Nenhum nó decide algo final (CLAUDE.md, seção 2): o grafo nunca avança
`current_module` sozinho, e ambos os nós terminam marcando
`human_approval_required=True`/`human_approval_status="pending"` sempre que
não seguem para o próximo nó da mesma invocação.

## `IntakeOutcome` — os 4 estados explícitos

Definido em `orchestrator/state.py`, usado por ambos os nós:

| Valor | Quando ocorre | O que significa |
|---|---|---|
| `completed` | Coordinator classificou com confiança, caso está no escopo Digital | Estado *interno* de transição — só existe para decidir se a triagem roda em seguida. Nunca é um estado final do caso. |
| `blocked` | `in_digital_scope=False` | Caso fora do escopo do Squad Digital — precisa ser encaminhado manualmente. Nenhum outro fluxo é inventado (CLAUDE.md, seção 2); a triagem nunca roda. |
| `awaiting_information` | `requires_more_information=True` (coordinator ou triage) | Dados insuficientes para classificar com confiança — `missing_information` lista o que falta, nunca fatos inventados. |
| `awaiting_human_review` | Triagem concluída normalmente | Classificação/checklist prontos, mas é só uma recomendação até um advogado aprovar. |

## Schemas de validação estruturada

Cada nó valida a saída bruta do modelo contra um schema Pydantic antes de
tocar no `CaseState` — falha de validação nunca produz um valor inventado,
sempre levanta `LLMOutputValidationError` (`orchestrator/graphs/intake.py`):

- **`CoordinatorRecommendation`**: `in_digital_scope`, `platform`,
  `fraud_type` (enum `FraudType`), `urgency` (enum `UrgencyLevel`),
  `requires_more_information`, `missing_information`, `out_of_scope_reason`,
  `rationale`. Espelha o "Output Esperado" de `coordinator.md`
  (PLATAFORMA RÉ / MODALIDADE / URGÊNCIA) em forma tipada.
- **`TriageRecommendation`**: `area` (enum `CaseArea`), `matter`, `urgency`,
  `case_summary`, `received_documents`, `missing_documents`,
  `requires_more_information`, `missing_information`, `rationale`. Espelha o
  "Output Esperado" de `triage.md` (ÁREA / MATÉRIA / SÍNTESE / DOCUMENTOS).

## Provedor de IA: `orchestrator/llm.py`

Nenhum nó chama a SDK de um provedor diretamente (CLAUDE.md, seção 15).
`LLMClient` é um `Protocol` com um único método,
`complete(*, model, system_prompt, user_input) -> StructuredLLMResult`
(`raw_output` ainda não validado — a validação de schema é sempre
responsabilidade do nó, nunca do client).

Este projeto **ainda não tem uma implementação concreta** (nenhuma chamada
real a um provedor foi feita — não há credenciais configuradas). O client é
injetado via o mecanismo nativo do LangGraph 1.x (`context_schema` +
`Runtime[ContextT]` — não `RunnableConfig`/`langchain_core`):

```python
@dataclass
class IntakeContext:
    llm_client: LLMClient

graph = StateGraph(CaseState, context_schema=IntakeContext)
...
result = await graph.ainvoke(state, context=IntakeContext(llm_client=meu_client))
```

Sem um `LLMClient` injetado, `coordinator`/`triage` levantam
`LLMNotConfiguredError` explicitamente — nunca caem para um provedor real
"por padrão" nem produzem uma classificação vazia silenciosa.

O nome do modelo nunca é hardcoded no nó: vem de
`settings.intake_llm_model` (`backend/app/core/config.py`).

## Auditoria

Cada chamada estruturada gera uma `AuditEntry` (`app/core/audit.py`):

- `actor="agent"`, `actor_id="coordinator"` ou `"triage"`.
- `input_data`/`output_data`: hasheados (SHA-256), nunca em claro.
- `model_used`/`tokens_used`/`duration_ms`: vêm do `StructuredLLMResult`.
- `metadata`: `build_prompt_audit_metadata(bundle)` (Fase 2.2) — versão e
  hash de cada uma das 4 camadas de prompt usadas — mais `outcome` e (na
  triagem) `recommended_next_module`.

`bootstrap_case` continua gerando sua própria entrada (`actor="system"`) — um
Intake completo com sucesso produz 3 entradas no `audit_trail`; um Intake
bloqueado ou aguardando informação produz 2 (sem a de `triage`).

## Persistência: `persist_intake_recommendation`

Depois de rodar o grafo, `persist_intake_recommendation(session, state)`
grava no `Case` (SQLAlchemy, Fase 2.1) o resultado mais recente:
`platform`, `fraud_type`, `urgency`, `area`, `matter`,
`human_review_required=True` e `status` (`PENDING_APPROVAL` quando
`intake_outcome == "awaiting_human_review"`, senão `IN_PROGRESS`).

Sempre filtra por `tenant_id` explícito (CLAUDE.md, seção 7) — nunca
localiza um caso só pelo `case_id`. Levanta `IntakeValidationError` se o
caso não existir para aquele tenant (nunca atualiza silenciosamente um caso
de outro tenant, e a RLS de `cases` bloqueia a leitura mesmo que a checagem
de aplicação seja contornada).

Chamada pela API HTTP em `app/services/intake_orchestration_service.py::run_intake`
(Fase 2.4 — ver docs/intake_api.md), que monta o `CaseState`, invoca o
grafo, e persiste `Case` + checkpoint + `audit_trail` na mesma transação.

## O que fica para depois

- **Implementação real de `LLMClient`**: hoje só existe o `Protocol` e um
  stub de teste (`backend/tests/llm_stubs.py::StubLLMClient`). A dependency
  FastAPI `get_llm_client` (`app/api/v1/intake.py`) sempre devolve `503` até
  uma implementação concreta (ex.: SDK da Anthropic, com credenciais via
  `.env`, nunca hardcoded) existir em `orchestrator/llm.py` ou um módulo
  irmão — nunca inline num nó.
- **Checklist de documentos apresentados**: `triage` só recomenda a lista de
  nomes faltantes (`documents_requested`) — o checklist estruturado em
  `case_documents` (Fase 2.1) continua sendo mantido separadamente via
  `POST/PATCH .../documents` (Fase 2.4), não é sincronizado automaticamente
  a partir da recomendação do grafo.

## Testes

- `backend/tests/test_intake_graph.py` — os 6 cenários exigidos: golpe PIX,
  marketplace, fora do escopo digital, informação insuficiente, isolamento
  entre tenants (via `persist_intake_recommendation`) e falha de validação
  de saída do modelo — todos com `StubLLMClient`, nenhuma chamada real.
- `backend/tests/test_orchestrator.py` — smoke test do grafo completo
  (mantido para compatibilidade com a suíte já existente da Fase 1).
