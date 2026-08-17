"""Extratores de texto de evidências (Fase 3.2) — sem banco, sem armazenamento.

Cada extrator recebe os bytes do original e devolve um ExtractionResult com o
texto derivado, confiança e limitações. O original NUNCA é modificado — estes
extratores nem sequer conhecem o armazenamento (app/core/storage.py).

Roteamento por mime_type (mesma lista fechada de ALLOWED_MIME_TYPES):
- text/plain      -> decodificação direta (confiança 1.0)
- application/pdf -> texto nativo via pypdf; se o PDF for escaneado (sem
  camada de texto), OCR gerenciado via Google Cloud Vision
- image/*         -> OCR gerenciado via Google Cloud Vision

O OCR é gerenciado (Vision API) e não local: não há tesseract nem poppler no
container — ver docs/adr/0003-ocr-google-cloud-vision.md, que também registra o
tratamento de transferência internacional de dados sob a LGPD.

OCR nunca é apresentado como prova perfeita: todo resultado de OCR carrega
confiança < 1.0 e uma limitação explícita (roadmap 3.2). Quando a confiança
fica abaixo de `extraction_low_confidence_threshold`, o resultado é marcado com
`low_confidence=True` — um sinal de que a leitura automática é insuficiente e a
conferência humana é obrigatória. O sistema não tenta "melhorar" o texto com
IA: a decisão volta para o advogado (CLAUDE.md, seção 2).
"""

import io
from dataclasses import dataclass

import pypdf

from app.core.config import settings
from app.core.vision import (
    TOOL_NAME as _VISION_TOOL,
)
from app.core.vision import (
    TOOL_VERSION as _VISION_VERSION,
)
from app.core.vision import (
    VisionError,
    annotate_image,
    annotate_pdf,
)

_LIMITATION_OCR = (
    "Texto obtido por OCR — conteúdo derivado, sujeito a erros de leitura. "
    "Requer conferência humana contra o arquivo original."
)
_LIMITATION_PDF_TEXT = (
    "Texto extraído da camada nativa do PDF — a formatação e a ordem de "
    "leitura podem diferir do documento renderizado."
)
_LIMITATION_LOW_CONFIDENCE = (
    " Confiança abaixo do patamar aceitável: trate esta leitura como "
    "insuficiente e confira integralmente contra o original antes de usar."
)


class ExtractionError(RuntimeError):
    """Falha de extração — o original permanece intacto; o erro é rastreável."""


@dataclass(frozen=True)
class ExtractionResult:
    """Resultado de um extrator: texto derivado + metadados de confiança.

    Attributes:
        kind: Método usado ("plain_text" | "pdf_text" | "pdf_vision_ocr" |
            "image_vision_ocr").
        text: Texto extraído (derivado — nunca substitui o original).
        confidence: 0.0 a 1.0 — nunca apresentar como certeza.
        limitations: Aviso obrigatório sobre os limites do método.
        tool_name: Ferramenta usada (para a trilha de auditoria).
        tool_version: Versão da ferramenta.
        low_confidence: True quando a confiança ficou abaixo do patamar
            configurado. Sinaliza insuficiência para a revisão humana; não
            dispara nenhum reprocessamento automático.
    """

    kind: str
    text: str
    confidence: float
    limitations: str
    tool_name: str
    tool_version: str
    low_confidence: bool = False


def _is_low_confidence(confidence: float) -> bool:
    return confidence < settings.extraction_low_confidence_threshold


def _ocr_result(kind: str, text: str, confidence: float) -> ExtractionResult:
    """Monta o ExtractionResult de um OCR, já com o sinal de insuficiência."""
    low = _is_low_confidence(confidence)
    limitations = _LIMITATION_OCR + (_LIMITATION_LOW_CONFIDENCE if low else "")
    return ExtractionResult(
        kind=kind,
        text=text,
        confidence=confidence,
        limitations=limitations,
        tool_name=_VISION_TOOL,
        tool_version=_VISION_VERSION,
        low_confidence=low,
    )


def extract_plain_text(content: bytes) -> ExtractionResult:
    """Decodifica um arquivo text/plain (ex.: exportação de conversa).

    Args:
        content: Bytes do arquivo original.

    Returns:
        ExtractionResult com o texto decodificado (confiança 1.0).
    """
    text = content.decode("utf-8", errors="replace")
    return ExtractionResult(
        kind="plain_text",
        text=text,
        confidence=1.0,
        limitations=(
            "Decodificação direta de texto puro — caracteres inválidos foram "
            "substituídos por U+FFFD, se presentes."
        ),
        tool_name="python-utf8",
        tool_version="3",
    )


async def extract_pdf(content: bytes) -> ExtractionResult:
    """Extrai texto de um PDF — camada nativa; OCR gerenciado apenas se escaneado.

    Args:
        content: Bytes do PDF original.

    Returns:
        ExtractionResult com kind "pdf_text" (nativo) ou "pdf_vision_ocr"
        (escaneado).

    Raises:
        ExtractionError: Se o PDF for ilegível ou o OCR falhar.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ExtractionError(f"PDF ilegível: {type(exc).__name__}") from exc

    native_text = "\n\n".join(page.strip() for page in pages).strip()
    if native_text:
        # Camada de texto presente: nada é enviado para fora — sem custo de
        # OCR e sem transferência internacional de dados.
        return ExtractionResult(
            kind="pdf_text",
            text=native_text,
            confidence=0.95,
            limitations=_LIMITATION_PDF_TEXT,
            tool_name="pypdf",
            tool_version=pypdf.__version__,
        )

    # Sem camada de texto -> PDF escaneado: OCR gerenciado.
    max_pages = min(page_count, settings.extraction_max_ocr_pages)
    try:
        annotation = await annotate_pdf(content, max_pages=max_pages)
    except VisionError as exc:
        raise ExtractionError(f"OCR de PDF escaneado falhou: {exc}") from exc

    result = _ocr_result("pdf_vision_ocr", annotation.text, annotation.confidence)
    if page_count > settings.extraction_max_ocr_pages:
        result = ExtractionResult(
            **{
                **result.__dict__,
                "limitations": (
                    f"{result.limitations} OCR limitado às primeiras "
                    f"{settings.extraction_max_ocr_pages} páginas de {page_count}."
                ),
            }
        )
    return result


async def extract_image(content: bytes) -> ExtractionResult:
    """Roda OCR gerenciado numa imagem (print de conversa, comprovante fotografado).

    Args:
        content: Bytes da imagem original.

    Returns:
        ExtractionResult com kind "image_vision_ocr".

    Raises:
        ExtractionError: Se a imagem for ilegível ou o OCR falhar.
    """
    try:
        annotation = await annotate_image(content)
    except VisionError as exc:
        raise ExtractionError(f"OCR de imagem falhou: {exc}") from exc
    return _ocr_result("image_vision_ocr", annotation.text, annotation.confidence)


async def extract_content(mime_type: str, content: bytes) -> ExtractionResult:
    """Roteia a extração pelo mime_type validado no upload.

    Args:
        mime_type: MIME type já validado (ALLOWED_MIME_TYPES + magic bytes).
        content: Bytes do arquivo original.

    Returns:
        ExtractionResult do extrator adequado.

    Raises:
        ExtractionError: Se não houver extrator para o tipo ou a extração falhar.
    """
    if mime_type == "text/plain":
        return extract_plain_text(content)
    if mime_type == "application/pdf":
        return await extract_pdf(content)
    if mime_type.startswith("image/"):
        return await extract_image(content)
    raise ExtractionError(f"Sem extrator para o tipo {mime_type}")
