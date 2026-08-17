# ADR 0003 — OCR gerenciado via Google Cloud Vision, substituindo tesseract local

- **Status:** Aceito
- **Data:** 2026-08-17
- **Fase:** 3.2 — Pipeline de extração de conteúdo das evidências
- **Substitui:** a escolha de OCR local registrada implicitamente na Fase 3.2
  (tesseract + pdf2image/poppler), não a decisão de armazenamento do ADR 0001.

## Contexto

O pipeline de extração da Fase 3.2 usava **tesseract** (via `pytesseract`) para
OCR de imagens e **pdf2image + poppler** para rasterizar PDFs escaneados antes
do OCR. Isso impunha três custos:

1. **Peso de infraestrutura.** O container do backend precisava instalar
   `tesseract-ocr`, `tesseract-ocr-por` e `poppler-utils` via apt — binários
   nativos que inflam a imagem e precisam existir em qualquer host de produção
   (a infra de produção ainda está em aberto: Railway, Render ou VPS).
2. **Custo de CPU/memória por evidência.** Rasterizar PDF página a página e
   rodar OCR local prende o worker por minutos num upload grande.
3. **Acurácia.** As evidências típicas deste squad são print de conversa de
   WhatsApp, comprovante de PIX fotografado e BO escaneado — imagens de
   qualidade variável, exatamente onde o tesseract é mais fraco.

Preços verificados em 2026-08-17 (por 1.000 páginas, list price):

| Opção | Custo/1k págs |
|---|---|
| Google Cloud Vision (`DOCUMENT_TEXT_DETECTION`) | US$ 1,50 (1.000 págs/mês grátis) |
| AWS Textract (`DetectDocumentText`) | US$ 1,50 |
| Azure AI Document Intelligence (`Read`) | US$ 1,50 |
| Claude Haiku 4.5 (visão) | ~US$ 7,60 |
| Claude Sonnet 5 (visão) | ~US$ 32 |

No volume esperado do MVP (~450 páginas/mês), o OCR gerenciado cabe inteiro no
tier gratuito do Vision. **Preço não foi o critério de decisão** — infra e
acurácia foram.

Alternativas consideradas:

1. **Manter tesseract + poppler.** Zero custo de API, mas mantém os binários
   nativos, o consumo de CPU e a pior acurácia justamente no tipo de evidência
   mais comum do squad.
2. **AWS Textract.** Melhor acurácia de texto puro medida (~99,3%), mas **não
   está disponível na região `sa-east-1` (São Paulo)** e exige credenciais AWS
   com assinatura SigV4.
3. **Azure AI Document Intelligence.** Lida com tabelas nativamente, mas
   **`Brazil South` não consta** entre as regiões suportadas do serviço.
4. **Modelo multimodal (Claude Sonnet 5 com visão) como extrator primário.**
   Melhor em layout e extração de campos, ~20× o custo, e violaria a seção 15
   do CLAUDE.md se chamado fora de um nó LangGraph — o pipeline de extração roda
   em `BackgroundTasks`, fora do grafo.

## Decisão

Adotar **Google Cloud Vision (`DOCUMENT_TEXT_DETECTION`)** como OCR gerenciado,
numa arquitetura de duas camadas:

1. **PDF com camada de texto** → `pypdf`, local. Nada sai do servidor, custo
   zero, sem transferência internacional de dados.
2. **Imagem e PDF escaneado** → Vision API.

A Vision API aceita **PDF inline em base64**, então nada precisa ser rasterizado
localmente: `tesseract-ocr`, `tesseract-ocr-por`, `poppler-utils`, `pytesseract`,
`pdf2image` e `pillow` foram todos removidos do `Dockerfile` e do `pyproject.toml`.

Escolhido entre os três gerenciados porque: mesmo preço, tier gratuito que cobre
o MVP inteiro, e autenticação por **API key** simples (`?key=`) — sem SDK pesado
nem assinatura de requisição.

### Restrição que define o desenho

`files:asyncBatchAnnotate` (assíncrono, sem limite prático de páginas) **não
aceita API key** — exige service account e bucket no Cloud Storage. Usamos
portanto apenas os endpoints **síncronos**:

- `images:annotate` — imagens, base64 inline
- `files:annotate` — PDF, base64 inline, **máximo 5 páginas por requisição**

PDFs maiores são anotados em blocos, selecionando páginas pelo campo `pages` da
requisição, com teto em `EXTRACTION_MAX_OCR_PAGES` (padrão 10 páginas = 2
requisições). O arquivo original é reenviado a cada bloco; nada é reescrito.

### Sinal de insuficiência — sem reprocessamento por IA

Quando a confiança média fica abaixo de `EXTRACTION_LOW_CONFIDENCE_THRESHOLD`
(padrão 0.75), a extração é gravada com `low_confidence = true` e a interface
exige conferência humana explícita.

**O sistema não reprocessa nem "melhora" o texto com IA.** Foi uma decisão
deliberada: encadear um modelo multimodal para reescrever uma leitura ruim
produziria texto mais plausível sem nenhuma garantia de ser mais fiel ao
original — exatamente o risco que a seção 2 do CLAUDE.md proíbe. Baixa confiança
devolve a decisão ao advogado, não a outro modelo.

O veredito é persistido na linha imutável de `evidence_extractions` (migration
`b7c4e91a2f08`), não derivado na leitura: mudar o patamar depois não pode
reescrever retroativamente o julgamento de execuções que já foram conferidas.

## Consequências

### Positivas

- Container sem nenhum binário nativo de OCR; imagem menor e portável para
  qualquer host de produção.
- Sem consumo de CPU/memória do worker com rasterização e OCR.
- Melhor acurácia no tipo de evidência dominante do squad.
- Custo efetivamente zero no volume do MVP.

### Negativas e riscos

- **Dependência de rede.** Vision indisponível, cota estourada ou chave inválida
  fazem a extração terminar em `failed`, com `error_message` técnico e o original
  intacto — reprocessável pela rota existente. Não há degradação silenciosa para
  um OCR local; a ausência de `GOOGLE_VISION_API_KEY` é erro explícito
  (`VisionNotConfiguredError`).
- **Custo por página** passa a existir onde antes era zero. Mitigado pelo teto
  `EXTRACTION_MAX_OCR_PAGES` e pelo roteamento que manda PDF com camada de texto
  para o `pypdf`.
- **Linhas históricas** de `evidence_extractions` mantêm `kind` `image_ocr` /
  `pdf_ocr` (tesseract). Os novos são `image_vision_ocr` / `pdf_vision_ocr` — a
  distinção é proposital, para que a trilha de auditoria diga qual ferramenta
  produziu cada texto.

### Transferência internacional de dados (LGPD) — ponto de atenção jurídica

**A Cloud Vision API não tem região no Brasil** (usa endpoint global; oferece
apenas endpoints regionais `us-` e `eu-`). Enviar uma evidência para OCR é,
portanto, **transferência internacional de dados pessoais** sob a LGPD — e o
conteúdo é sensível: prints de conversa, comprovantes com CPF e dados bancários.

Isso **não é um defeito desta escolha em particular**: nenhum dos três OCRs
gerenciados avaliados tem região brasileira (Textract não atende `sa-east-1`;
Document Intelligence não atende `Brazil South`), e o mesmo vale para a API da
Anthropic usada pelos nós do grafo. A alternativa sem transferência é voltar ao
OCR local, com os custos descritos no Contexto.

Pendências que **precisam ser resolvidas antes de produção com dados reais** —
nenhuma delas é bloqueante para o ambiente de desenvolvimento:

- [ ] Definir a base legal e o mecanismo de transferência (cláusulas-padrão
      contratuais da ANPD, ou roteamento para região da UE, coberta pela decisão
      de adequação recíproca Brasil–UE da Resolução CD/ANPD nº 32/2026).
- [ ] Registrar a operação no ROPA do escritório e revisar a política de
      privacidade / termo com o cliente titular dos dados.
- [ ] Avaliar a política de retenção do Google Cloud para o conteúdo enviado à
      Vision API e desativar qualquer uso secundário disponível.
- [ ] Restringir a API key à Cloud Vision API (**já feito**) e rotacioná-la
      periodicamente.

Enquanto essas pendências não fecharem, o ambiente de desenvolvimento deve usar
apenas evidências fictícias.

## Referências

- Preços: <https://cloud.google.com/vision/pricing>
- Limite de 5 páginas no `files:annotate`:
  <https://docs.cloud.google.com/vision/docs/file-small-batch>
- API key não suportada em `files:asyncBatchAnnotate`:
  <https://docs.cloud.google.com/vision/docs/pdf>
- Transferência internacional / ANPD:
  <https://www.gov.br/anpd/pt-br/assuntos/assuntos-internacionais/transferencia-internacional-de-dados>
- Implementação: `backend/app/core/vision.py`, `backend/app/core/extraction.py`
- Migration do sinal de insuficiência: `b7c4e91a2f08`
