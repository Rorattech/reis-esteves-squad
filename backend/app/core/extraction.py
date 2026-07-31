"""Extratores de texto de evidências (Fase 3.2) — puros, sem banco.

Cada extrator recebe os bytes do original e devolve um ExtractionResult com o
texto derivado, confiança e limitações. O original NUNCA é modificado — estes
extratores nem sequer conhecem o armazenamento (app/core/storage.py).

Roteamento por mime_type (mesma lista fechada de ALLOWED_MIME_TYPES):
- text/plain  -> decodificação direta (confiança 1.0)
- application/pdf -> texto nativo via pypdf; se o PDF for escaneado (sem
  camada de texto), rasteriza com pdf2image e roda OCR página a página
- image/*     -> OCR com tesseract (idioma português + inglês)

OCR nunca é apresentado como prova perfeita: todo resultado de OCR carrega
confiança < 1.0 e uma limitação explícita (roadmap 3.2).
"""

import io
from dataclasses import dataclass

import pypdf
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

_OCR_LANG = "por+eng"
# Limite defensivo de páginas rasterizadas por PDF escaneado — evita que um
# upload de 50MB prenda o worker por minutos.
_MAX_OCR_PAGES = 10

_LIMITATION_OCR = (
    "Texto obtido por OCR — conteúdo derivado, sujeito a erros de leitura. "
    "Requer conferência humana contra o arquivo original."
)
_LIMITATION_PDF_TEXT = (
    "Texto extraído da camada nativa do PDF — a formatação e a ordem de "
    "leitura podem diferir do documento renderizado."
)


class ExtractionError(RuntimeError):
    """Falha de extração — o original permanece intacto; o erro é rastreável."""


@dataclass(frozen=True)
class ExtractionResult:
    """Resultado de um extrator: texto derivado + metadados de confiança.

    Attributes:
        kind: Método usado ("plain_text" | "pdf_text" | "pdf_ocr" | "image_ocr").
        text: Texto extraído (derivado — nunca substitui o original).
        confidence: 0.0 a 1.0 — nunca apresentar como certeza.
        limitations: Aviso obrigatório sobre os limites do método.
        tool_name: Ferramenta usada (para a trilha de auditoria).
        tool_version: Versão da ferramenta.
    """

    kind: str
    text: str
    confidence: float
    limitations: str
    tool_name: str
    tool_version: str


def _tesseract_version() -> str:
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:  # pragma: no cover — tesseract ausente do host
        return "unknown"


def _ocr_image(image: Image.Image) -> tuple[str, float]:
    """Roda OCR numa imagem e devolve (texto, confiança média das palavras)."""
    data = pytesseract.image_to_data(
        image, lang=_OCR_LANG, output_type=pytesseract.Output.DICT
    )
    words: list[str] = []
    confidences: list[float] = []
    for word, conf in zip(data["text"], data["conf"]):
        if not word.strip():
            continue
        words.append(word)
        confidence = float(conf)
        if confidence >= 0:  # tesseract usa -1 para blocos sem confiança
            confidences.append(confidence)
    text = pytesseract.image_to_string(image, lang=_OCR_LANG)
    mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    return text.strip(), round(mean_confidence, 3)


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


def extract_pdf(content: bytes) -> ExtractionResult:
    """Extrai texto de um PDF — camada nativa; OCR apenas se for escaneado.

    Args:
        content: Bytes do PDF original.

    Returns:
        ExtractionResult com kind "pdf_text" (nativo) ou "pdf_ocr" (escaneado).

    Raises:
        ExtractionError: Se o PDF for ilegível ou o OCR falhar.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ExtractionError(f"PDF ilegível: {type(exc).__name__}") from exc

    native_text = "\n\n".join(page.strip() for page in pages).strip()
    if native_text:
        return ExtractionResult(
            kind="pdf_text",
            text=native_text,
            confidence=0.95,
            limitations=_LIMITATION_PDF_TEXT,
            tool_name="pypdf",
            tool_version=pypdf.__version__,
        )

    # Sem camada de texto -> PDF escaneado: rasteriza e roda OCR por página.
    try:
        images = convert_from_bytes(content, last_page=_MAX_OCR_PAGES)
        page_results = [_ocr_image(image) for image in images]
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"OCR de PDF escaneado falhou: {type(exc).__name__}") from exc

    text = "\n\n".join(page_text for page_text, _ in page_results).strip()
    confidences = [confidence for _, confidence in page_results if confidence > 0]
    mean_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    limitations = _LIMITATION_OCR
    if len(pages) > _MAX_OCR_PAGES:
        limitations += f" OCR limitado às primeiras {_MAX_OCR_PAGES} páginas."
    return ExtractionResult(
        kind="pdf_ocr",
        text=text,
        confidence=mean_confidence,
        limitations=limitations,
        tool_name="tesseract+pdf2image",
        tool_version=_tesseract_version(),
    )


def extract_image(content: bytes) -> ExtractionResult:
    """Roda OCR numa imagem (print de conversa, comprovante fotografado).

    Args:
        content: Bytes da imagem original.

    Returns:
        ExtractionResult com kind "image_ocr".

    Raises:
        ExtractionError: Se a imagem for ilegível ou o OCR falhar.
    """
    try:
        image = Image.open(io.BytesIO(content))
        text, confidence = _ocr_image(image)
    except Exception as exc:
        raise ExtractionError(f"OCR de imagem falhou: {type(exc).__name__}") from exc
    return ExtractionResult(
        kind="image_ocr",
        text=text,
        confidence=confidence,
        limitations=_LIMITATION_OCR,
        tool_name="tesseract",
        tool_version=_tesseract_version(),
    )


def extract_content(mime_type: str, content: bytes) -> ExtractionResult:
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
        return extract_pdf(content)
    if mime_type.startswith("image/"):
        return extract_image(content)
    raise ExtractionError(f"Sem extrator para o tipo {mime_type}")
