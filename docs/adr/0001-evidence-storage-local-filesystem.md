# ADR 0001 — Armazenamento de originais de evidência em sistema de arquivos local

- **Status:** Aceito
- **Data:** 2026-07-31
- **Fase:** 3.1 — Upload seguro e inventário de evidências

## Contexto

A Fase 3 exige guardar o arquivo original de cada evidência digital intacto, com
hash de integridade, isolamento por tenant e acesso exclusivamente autenticado
(docs/roadmap_mvp_squad_digital.md, seção 3.1). A stack obrigatória do projeto
(CLAUDE.md, seção 3) não define um provedor de object storage para o MVP — e a
infraestrutura de produção ainda está em aberto (Railway, Render ou VPS própria).

Alternativas consideradas:

1. **S3 (AWS) ou compatível gerenciado** — adiciona dependência externa, custo e
   credenciais novas antes de a infra de produção estar definida.
2. **MinIO self-hosted no docker-compose** — mais um serviço para operar, com a
   mesma superfície de API do S3, sem necessidade real no MVP (um único backend,
   um único host).
3. **Sistema de arquivos local em volume Docker dedicado** — menor solução
   compatível com a stack atual; nenhum serviço novo.

## Decisão

Armazenar os originais em **sistema de arquivos local**, num diretório privado
(`EVIDENCE_STORAGE_DIR`, padrão `/app/storage/evidence`) montado como volume
Docker dedicado (`evidence_storage` em `infra/docker-compose.yml`), fora dos
bind mounts de código e nunca servido como conteúdo estático.

Regras de implementação (`backend/app/core/storage.py`):

- **Layout físico por tenant:** `<tenant_id>/<case_id>/<evidence_id>/original.<ext>` —
  isolamento físico como segunda camada além do filtro `tenant_id` + RLS.
- **Escrita única:** cada `storage_key` é gravada com criação exclusiva
  (open `"xb"`); sobrescrita é erro de estado, nunca silenciosa — o original é
  imutável (roadmap 3.1: "Não modificar o arquivo original").
- **Extensão derivada do MIME type validado** (lista fechada + verificação de
  magic bytes), nunca do nome de arquivo enviado pelo cliente.
- **Sem URL pública:** o conteúdo só sai pela rota autenticada
  `GET /api/v1/cases/{case_id}/evidence/{evidence_id}/download`, com RBAC e
  registro de acesso em `audit_logs`. A `storage_key` nunca aparece em resposta
  de API.
- **Proteção contra path traversal:** toda resolução de caminho é validada como
  descendente do diretório raiz.

Texto extraído e artefatos derivados (Fase 3.2 — OCR/transcrição) serão
armazenados separadamente do original, nunca no mesmo arquivo.

## Consequências

- **Positivas:** zero dependências novas; backup trivial (volume Docker);
  a interface `EvidenceStorage` concentra todo o acesso a disco — trocar por
  S3/MinIO no futuro exige apenas uma nova implementação da mesma interface,
  sem mudanças em `app/services/evidence_service.py` ou nas rotas.
- **Negativas:** não escala horizontalmente (múltiplas réplicas do backend
  exigiriam volume compartilhado ou migração para object storage); durabilidade
  depende do backup do host. Aceitável para o MVP de piloto interno.
- **Gatilho de revisão:** definir a infra de produção (CLAUDE.md, seção 3) ou
  precisar de mais de uma réplica do backend reabre esta decisão.
