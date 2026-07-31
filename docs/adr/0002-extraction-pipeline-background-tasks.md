# ADR 0002 — Pipeline de extração via BackgroundTasks do FastAPI

- **Status:** Aceito
- **Data:** 2026-07-31
- **Fase:** 3.2 — Pipeline de OCR, transcrição e normalização

## Contexto

A Fase 3.2 exige extração assíncrona de texto (PDF nativo, OCR de imagens e
PDFs escaneados) sem bloquear a resposta do upload. O roadmap pede para
inspecionar a infraestrutura existente e, na ausência de uma solução definida,
implementar a menor compatível com a arquitetura, documentando a decisão.

Estado atual do repositório: não há fila de tarefas nem worker dedicado. O
stack tem Redis (cache) e n8n (automação via webhook, nunca exposto ao
cliente), mas nenhum dos dois está integrado a processamento de evidências.

Alternativas consideradas:

1. **Celery/arq + Redis** — worker dedicado, retry e visibilidade, ao custo de
   um serviço novo, configuração de broker e mais uma superfície de deploy.
2. **n8n via webhook** — delegaria o pipeline à automação, mas exigiria expor
   endpoint interno de callback, tratar autenticação de máquina e mover a
   lógica de extração para fora do backend tipado/testado.
3. **BackgroundTasks do FastAPI/Starlette** — tarefa pós-resposta no mesmo
   processo; zero infraestrutura nova.

## Decisão

Usar **BackgroundTasks** (`app/services/extraction_service.py::process_evidence`),
disparado após o commit do upload e pela rota explícita de reprocessamento
(`POST .../evidence/{id}/process`).

Regras de implementação:

- A tarefa abre a própria sessão com `tenant_scoped_session(tenant_id)`
  (`app/core/db.py`) — o tenant vem do JWT da request que disparou a tarefa,
  nunca de input do usuário; RLS continua valendo.
- Transições de status: `received/processed/failed → processing → processed | failed`.
  Reprocessar com status `processing` é rejeitado (409) — sem execuções
  concorrentes da mesma evidência.
- Cada execução é uma linha imutável em `evidence_extractions` (ferramenta,
  versão, hashes de entrada/saída, duração, confiança, limitações) — reprocessos
  criam linhas novas, nunca sobrescrevem.
- Falhas terminam em status `failed` com `error_message` técnico e auditoria —
  nunca derrubam a request nem tocam o original.
- Logs e audit_logs carregam hashes e métricas, nunca o texto extraído
  (CLAUDE.md, seção 12).

## Consequências

- **Positivas:** zero serviços novos; pipeline testável na própria suíte
  (ASGITransport executa BackgroundTasks ao fim da request); latência de
  disparo nula.
- **Negativas:** a tarefa morre com o processo (sem retry automático — o
  reprocessamento manual cobre o caso); OCR pesado compete por CPU com a API.
  Aceitável para o MVP de piloto interno com uma réplica.
- **Gatilho de revisão:** volume real de OCR degradando a latência da API, ou
  necessidade de retry automático/fila — migrar para worker dedicado (arq ou
  Celery sobre o Redis já existente), mantendo `process_evidence` como está.
