"""Cliente do Google Cloud Vision — OCR gerenciado de imagens e PDFs escaneados.

Decisão registrada em docs/adr/0003-ocr-google-cloud-vision.md. Substitui o par
tesseract + poppler, que exigia binários nativos no container: a Vision API
aceita PDF inline em base64, então nada precisa ser rasterizado localmente.

Autenticação por API key restrita à Vision API (query param `?key=`). O endpoint
assíncrono `files:asyncBatchAnnotate` **não aceita API key** — exige service
account e bucket no Cloud Storage. Por isso este módulo usa apenas os endpoints
síncronos, e daí vem o teto de 5 páginas por requisição (`files:annotate`):
PDFs maiores são anotados em blocos, selecionando páginas via campo `pages`.

Nenhum log deste módulo carrega conteúdo de documento nem texto extraído
(CLAUDE.md, seção 12) — apenas contagens, códigos de erro e duração.
"""

import base64
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

TOOL_NAME = "google-cloud-vision"
TOOL_VERSION = "v1"

_FEATURE_DOCUMENT_TEXT = "DOCUMENT_TEXT_DETECTION"

# Teto de conteúdo inline por requisição. A Vision API rejeita payloads JSON
# grandes; base64 infla os bytes em ~33%, então limitamos os bytes crus.
_MAX_INLINE_BYTES = 7 * 1024 * 1024


class VisionError(RuntimeError):
    """Falha ao anotar um arquivo na Vision API — o original permanece intacto."""


class VisionNotConfiguredError(VisionError):
    """Levantada quando `GOOGLE_VISION_API_KEY` não está definida.

    Nunca há degradação silenciosa para um OCR local: a ausência da chave é um
    erro explícito e rastreável, mesmo princípio de `PromptLoadError` em
    `app/core/prompts.py` e de `LLMNotConfiguredError` em `orchestrator/llm.py`.
    """


@dataclass(frozen=True)
class VisionAnnotation:
    """Texto e confiança devolvidos pela Vision API para um arquivo ou bloco.

    Attributes:
        text: Texto reconhecido, já concatenado na ordem das páginas.
        confidence: Média das confianças de página (0.0 a 1.0). 0.0 quando a
            API não devolve confiança — nunca interpretar como certeza.
        pages_annotated: Quantas páginas foram efetivamente anotadas.
    """

    text: str
    confidence: float
    pages_annotated: int


def _api_key() -> str:
    if not settings.google_vision_api_key:
        raise VisionNotConfiguredError(
            "GOOGLE_VISION_API_KEY não configurada — o OCR gerenciado está "
            "indisponível (ver .env.example e docs/adr/0003-ocr-google-cloud-vision.md)."
        )
    return settings.google_vision_api_key


def _guard_payload_size(content: bytes) -> None:
    if len(content) > _MAX_INLINE_BYTES:
        raise VisionError(
            f"Arquivo grande demais para anotação inline "
            f"({len(content)} bytes > {_MAX_INLINE_BYTES})."
        )


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Envia uma requisição à Vision API e devolve o corpo JSON.

    Args:
        path: Caminho do endpoint (ex.: "images:annotate").
        payload: Corpo já montado da requisição.

    Returns:
        Corpo JSON da resposta.

    Raises:
        VisionError: Em erro de rede, timeout, status HTTP != 200 ou resposta
            ilegível. A mensagem nunca inclui a API key nem conteúdo do arquivo.
    """
    url = f"{settings.google_vision_endpoint.rstrip('/')}/{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.google_vision_timeout_seconds) as client:
            response = await client.post(url, params={"key": _api_key()}, json=payload)
    except httpx.HTTPError as exc:
        # str(exc) do httpx pode ecoar a URL — e a URL carrega a API key.
        raise VisionError(f"Falha de rede ao chamar a Vision API: {type(exc).__name__}") from exc

    if response.status_code != 200:
        # Corpo de erro da Vision descreve o problema (chave inválida, cota,
        # tipo não suportado) sem repetir o conteúdo enviado.
        raise VisionError(
            f"Vision API respondeu {response.status_code}: "
            f"{_error_message(response) or 'sem detalhe'}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise VisionError("Resposta da Vision API não é JSON válido.") from exc


def _error_message(response: httpx.Response) -> str | None:
    try:
        return str(response.json().get("error", {}).get("message"))[:300]
    except Exception:  # pragma: no cover — corpo de erro não-JSON
        return None


def _parse_annotation(raw_responses: list[dict[str, Any]]) -> VisionAnnotation:
    """Extrai texto e confiança média de uma lista de respostas da Vision.

    Args:
        raw_responses: Lista `responses` da Vision (uma entrada por página, no
            caso de arquivos, ou uma única entrada no caso de imagens).

    Returns:
        VisionAnnotation com o texto concatenado e a confiança média.

    Raises:
        VisionError: Se alguma entrada trouxer o campo `error`.
    """
    texts: list[str] = []
    confidences: list[float] = []
    annotated = 0

    for entry in raw_responses:
        if entry.get("error"):
            message = str(entry["error"].get("message", "erro sem detalhe"))[:300]
            raise VisionError(f"Vision API não anotou o arquivo: {message}")
        full_text = entry.get("fullTextAnnotation")
        if not full_text:
            # Página em branco (ou sem texto reconhecível) não é erro.
            annotated += 1
            continue
        annotated += 1
        texts.append(str(full_text.get("text", "")).strip())
        for page in full_text.get("pages", []):
            page_confidence = page.get("confidence")
            if isinstance(page_confidence, (int, float)) and page_confidence > 0:
                confidences.append(float(page_confidence))

    mean_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    text = "\n\n".join(part for part in texts if part).strip()
    return VisionAnnotation(text=text, confidence=mean_confidence, pages_annotated=annotated)


async def annotate_image(content: bytes) -> VisionAnnotation:
    """Roda OCR numa imagem (print de conversa, comprovante fotografado).

    Args:
        content: Bytes da imagem original.

    Returns:
        VisionAnnotation com o texto reconhecido e a confiança média.

    Raises:
        VisionNotConfiguredError: Se a API key não estiver configurada.
        VisionError: Em falha de rede, cota, ou recusa da Vision API.
    """
    _guard_payload_size(content)
    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(content).decode()},
                "features": [{"type": _FEATURE_DOCUMENT_TEXT}],
            }
        ]
    }
    body = await _post("images:annotate", payload)
    annotation = _parse_annotation(body.get("responses", []))
    logger.info(
        "vision.image.annotated",
        confidence=annotation.confidence,
        text_chars=len(annotation.text),
    )
    return annotation


async def annotate_pdf(content: bytes, *, max_pages: int) -> VisionAnnotation:
    """Roda OCR num PDF escaneado, em blocos de páginas.

    `files:annotate` anota no máximo 5 páginas por requisição, então o PDF é
    percorrido em blocos desse tamanho até `max_pages`. O arquivo original é
    reenviado a cada bloco com uma seleção diferente de páginas — nada é
    reescrito nem rasterizado localmente.

    Args:
        content: Bytes do PDF original.
        max_pages: Teto de páginas a submeter (ver `extraction_max_ocr_pages`).

    Returns:
        VisionAnnotation com o texto de todos os blocos concatenado.

    Raises:
        VisionNotConfiguredError: Se a API key não estiver configurada.
        VisionError: Em falha de rede, cota, ou recusa da Vision API.
    """
    _guard_payload_size(content)
    encoded = base64.b64encode(content).decode()
    block_size = max(1, settings.google_vision_pages_per_request)

    texts: list[str] = []
    weighted_confidence = 0.0
    annotated = 0

    for start in range(1, max_pages + 1, block_size):
        pages = list(range(start, min(start + block_size, max_pages + 1)))
        payload = {
            "requests": [
                {
                    "inputConfig": {"content": encoded, "mimeType": "application/pdf"},
                    "features": [{"type": _FEATURE_DOCUMENT_TEXT}],
                    "pages": pages,
                }
            ]
        }
        body = await _post("files:annotate", payload)
        # files:annotate aninha uma resposta por página dentro de responses[0].
        file_response = (body.get("responses") or [{}])[0]
        if file_response.get("error"):
            message = str(file_response["error"].get("message", "erro sem detalhe"))[:300]
            # Pedir páginas além do fim do documento é o fim normal do laço,
            # não uma falha: encerra o que já foi anotado.
            if annotated and "page" in message.lower():
                break
            raise VisionError(f"Vision API não anotou o PDF: {message}")

        block = _parse_annotation(file_response.get("responses", []))
        if block.pages_annotated == 0:
            break
        if block.text:
            texts.append(block.text)
        weighted_confidence += block.confidence * block.pages_annotated
        annotated += block.pages_annotated
        if block.pages_annotated < len(pages):
            # Bloco veio incompleto: o documento acabou antes de max_pages.
            break

    confidence = round(weighted_confidence / annotated, 3) if annotated else 0.0
    annotation = VisionAnnotation(
        text="\n\n".join(texts).strip(), confidence=confidence, pages_annotated=annotated
    )
    logger.info(
        "vision.pdf.annotated",
        pages=annotation.pages_annotated,
        confidence=annotation.confidence,
        text_chars=len(annotation.text),
    )
    return annotation
