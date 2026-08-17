# Fase 3 — Evidências: upload, extração, análise e interface

Base de gestão de evidências do módulo `evidence`: receber, validar, armazenar
intacto, inventariar e auditar. **Nenhuma análise jurídica acontece nesta etapa**
(roadmap 3.1) — OCR/extração é a Fase 3.2; os nós LangGraph são a 3.3; a
interface (Central de evidências) chega nas 3.4/3.5.

## Componentes

| Arquivo | Papel |
|---|---|
| `backend/app/models/evidence_file.py` | ORM `evidence_files` — metadados + hash + status de processamento |
| `backend/app/models/schemas/evidence_file.py` | `EvidenceFileResponse` (nunca expõe `storage_key`) |
| `backend/app/core/storage.py` | `EvidenceStorage` — originais em disco privado, escrita única |
| `backend/app/services/evidence_service.py` | Validação, dedup por hash, inventário e auditoria |
| `backend/app/api/v1/evidence.py` | Rotas autenticadas sob `/api/v1/cases/{case_id}/evidence` |
| `backend/alembic/versions/f39dd1e27be8_*.py` | Migration `evidence_files` + enum + RLS |
| `backend/app/core/vision.py` | Cliente do Google Cloud Vision — OCR gerenciado de imagem e PDF escaneado |
| `docs/adr/0001-evidence-storage-local-filesystem.md` | Decisão de armazenamento (filesystem local, volume Docker) |
| `docs/adr/0003-ocr-google-cloud-vision.md` | Decisão de OCR gerenciado + pendências de LGPD (transferência internacional) |

## Fluxo de upload

1. `POST /api/v1/cases/{case_id}/evidence` (multipart) — exige JWT e papel
   `admin | lawyer | paralegal` (viewer só lê o inventário).
2. O serviço confirma que o caso pertence ao tenant do JWT (RLS é a segunda
   camada), valida MIME type (lista fechada: pdf, jpg, png, webp, txt), tamanho
   (`BACKEND_MAX_UPLOAD_MB`) e conteúdo (magic bytes ≠ nome do arquivo).
3. Calcula SHA-256; se já existir evidência com o mesmo hash **no tenant**,
   marca `duplicate_of_id` (o upload segue como registro/original independente —
   cada envio é um evento de custódia distinto).
4. Grava o original em `EVIDENCE_STORAGE_DIR` no layout
   `<tenant_id>/<case_id>/<evidence_id>/original.<ext>`, com criação exclusiva —
   um original nunca é sobrescrito.
5. Registra em `audit_logs` (actor humano, `metadata.entity = "evidence"`, IP de
   origem) e retorna os metadados com `status: "received"`.

## Estados de processamento

`received → processing → processed | failed` (`EvidenceProcessingStatus`).
O upload cria em `received` e dispara o pipeline em background; as transições
são do pipeline da Fase 3.2 (abaixo).

## Pipeline de extração (Fase 3.2)

Mecanismo: BackgroundTasks do FastAPI (ADR 0002) — disparado no upload e pela
rota `POST .../evidence/{id}/process` (reprocessamento; 409 se já estiver
`processing`). A tarefa abre sessão própria escopada pelo tenant do JWT
(`tenant_scoped_session` em `app/core/db.py`) — RLS continua valendo.

Extratores (`app/core/extraction.py`), roteados pelo MIME validado no upload:

| Tipo | Método (`kind`) | Confiança |
|---|---|---|
| `text/plain` | `plain_text` — decodificação direta | 1.0 |
| PDF com camada de texto | `pdf_text` — pypdf (local, nada sai do servidor) | 0.95 |
| PDF escaneado | `pdf_vision_ocr` — Google Cloud Vision (máx. 10 págs) | média das páginas |
| Imagens | `image_vision_ocr` — Google Cloud Vision | média das páginas |

**O OCR é gerenciado, não local** (ADR 0003): não há tesseract nem poppler no
container. A Vision API aceita PDF inline em base64, então nada é rasterizado
localmente. Como `files:asyncBatchAnnotate` não aceita API key, usamos os
endpoints síncronos — daí o teto de 5 páginas por requisição, e PDFs maiores
serem anotados em blocos (`app/core/vision.py`).

⚠️ Isso implica **transferência internacional de dados pessoais**: a Vision API
não tem região no Brasil. As pendências de LGPD a resolver antes de produção com
dados reais estão listadas no ADR 0003.

Cada execução é uma linha **imutável** em `evidence_extractions` (ferramenta,
versão, hash de entrada/saída, duração, confiança, `limitations` obrigatório) —
reprocessos criam linhas novas; falhas terminam em `failed` com `error_message`
técnico, sem tocar o original. Todo resultado de OCR carrega aviso explícito de
que é conteúdo derivado sujeito a erro. `GET .../evidence/{id}/extractions`
lista as execuções com o texto derivado.

### Sinal de insuficiência (`low_confidence`)

Confiança abaixo de `EXTRACTION_LOW_CONFIDENCE_THRESHOLD` (padrão 0.75) grava
`low_confidence = true` na linha da extração, e o detalhe da evidência destaca
"Conferência humana obrigatória". O texto derivado **não é descartado** — baixa
confiança sinaliza, não invalida.

O sistema **não reprocessa nem "melhora" o texto com IA**: encadear um modelo
multimodal produziria texto mais plausível sem garantia de ser mais fiel ao
original. A decisão volta para o advogado (CLAUDE.md, seção 2). O veredito é
persistido, não derivado na leitura, para que mudar o patamar depois não
reescreva o julgamento de execuções já conferidas.

## Análise de evidências — nós LangGraph (Fase 3.3)

`orchestrator/graphs/evidence.py`: `bootstrap_evidence` → `documental`
(inventário probatório rastreável) → `specialist` (leitura técnica da
plataforma). O LLM entra só via `LLMClient` injetado (`EvidenceContext`);
prompts em `prompts/digital/evidence/{documental,specialist}.md`.

Desde a Fase 2.7 os dois nós recebem também o **código do caso**
(`case_code`), e o `specialist` recebe **município e UF do cliente** — é o que
permite recomendar o foro do consumidor (CDC art. 101, I), que o prompt sempre
pediu e não tinha como responder. Nome, CPF, RG e endereço completo **não**
trafegam: o cabeçalho dos relatórios identifica o processo pelo código, nunca
pela pessoa (ver `docs/phase_2_intake_domain.md`).

Garantias implementadas no grafo (não no prompt):

- **Rastreabilidade forçada**: achado `fact`/`inference` sem
  `source_evidence_id` válido, ou item de inventário apontando evidência
  inexistente, levanta `EvidenceTraceabilityError` (HTTP 502) — o modelo não
  consegue inventar provas que o sistema aceite.
- **Fato × inferência × lacuna**: todo achado tem `category`
  (`fact | inference | missing_info`); lacunas são os únicos sem evidência de
  origem e alimentam `documents_requested` (pendências documentais).
- **Revisão humana obrigatória**: o grafo termina sempre em
  `evidence_outcome="awaiting_human_review"` + `human_approval_required=True`;
  achados nascem `DRAFT_PENDING_REVIEW` na tabela `evidence_findings` (RLS).

Rotas (`/api/v1/cases/{id}/evidence/analysis/...`): `POST run` (422 se o
intake não foi aprovado ou não há evidência), `GET result`, `POST review`
(`approve` → achados APPROVED + caso avança para `research`;
`return_for_information` → caso permanece em `evidence`). Orquestração em
`app/services/evidence_orchestration_service.py`: achados persistidos,
checkpoint do CaseState e audit_trail na mesma transação.

## Revisão humana do texto extraído (backend da Fase 3.5)

`POST .../evidence/{id}/extractions/{extraction_id}/review` com
`{verdict: "confirmed" | "extraction_error", note}` grava uma linha em
`evidence_extraction_reviews` + auditoria. A correção humana é um **registro**,
nunca uma substituição do texto derivado ou do original.

## Acesso ao conteúdo

- `GET .../evidence` e `GET .../evidence/{id}` — inventário/metadados (qualquer
  papel autenticado do tenant).
- `GET .../evidence/{id}/download` — único caminho para o arquivo original;
  exige papel operacional e **gera entrada de auditoria a cada acesso** (cadeia
  de custódia). Não existe URL pública nem permanente.

## Cadeia de custódia simplificada

Derivada de `audit_logs` filtrando `metadata.entity = "evidence"` e
`metadata.evidence_id`: quem enviou (upload), quem acessou (download) e, na Fase
3.2, quais processamentos rodaram. Sem tabela própria — evita duplicar o que
`audit_logs` já garante com tenant_id + RLS.

## Testes

`backend/tests/test_evidence_api.py`: upload com hash e original intacto em
disco, tipo inválido, conteúdo incompatível com o MIME declarado, arquivo vazio,
duplicata no mesmo tenant, mesmo hash em outro tenant (não é duplicata),
isolamento cross-tenant (404), RBAC de viewer (403 upload/download, 200
inventário), download auditado e caso inexistente. Rodar com `make test`
(stack Docker de pé — os testes usam o Postgres real, nunca SQLite).

## Interface — Central de Evidências e detalhe (Fases 3.4/3.5)

`/cases/{caseId}/evidencias` (Central de Evidências):

- **Upload** (`EvidenceUpload`): um ou mais arquivos em sequência, validação
  visual espelhando a do backend (tipos, 50MB, vazio) — a validação real é
  sempre do servidor; aviso de que o original é preservado intacto.
- **Inventário de arquivos** (`EvidenceInventoryTable`): nome, tipo, tamanho,
  status real (`Recebido | Processando | Processado | Falhou`), origem, badge
  de duplicidade; ações de detalhe, download (blob autenticado — sem URL
  pública) e reprocessamento.
- **Pendências documentais**: reutiliza `CaseDocumentChecklist`, com as
  lacunas apontadas pela análise de evidências como sugestões.
- **Inventário probatório** (`EvidenceAnalysisPanel`): executa a análise,
  lista achados por categoria (fato/inferência/lacuna) com confiança e origem,
  leitura técnica do specialist marcada como rascunho, e a decisão humana —
  aprovar (com confirmação; avança para pesquisa) ou devolver (justificativa
  obrigatória).

`/cases/{caseId}/evidencias/{evidenceId}` (detalhe — Fase 3.5):

- Metadados + hash SHA-256 + custódia; visualização protegida do original
  (`EvidenceOriginalViewer` — object URL efêmera de blob autenticado; tipos
  não visualizáveis caem para download).
- Conteúdo extraído (`ExtractionPanel`) com aviso fixo de conteúdo derivado,
  confiança, limitações e falhas rastreáveis; revisão humana (confirmar /
  apontar erro com observação) que registra sem substituir nada.
- Achados do inventário ligados à evidência.

Estados cobertos: carregamento, vazio, erro de API, acesso negado (403 do
backend) e papel viewer (só leitura — sem upload, download ou revisão).
Testes em `page.test.tsx` de cada rota (vitest + testing-library).
