"""Testes do pipeline de extração (Fase 3.2) e da revisão humana (Fase 3.5).

Cobertura pedida no roadmap 3.2: PDF textual, imagem, arquivo inválido,
falha de OCR e isolamento entre tenants. O pipeline roda via BackgroundTasks
(ADR 0002) — com ASGITransport, as tarefas executam antes de a chamada do
cliente retornar, então os testes leem o resultado logo após o upload.

O OCR é gerenciado (Google Cloud Vision — ver app/core/vision.py), então todo
teste que passa por OCR **mocka a Vision API**: a suíte nunca faz chamada de
rede, nunca consome cota e nunca depende de uma API key estar configurada.
"""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

import app.core.extraction as extraction
import app.services.extraction_service as extraction_service
from app.core.extraction import ExtractionError, ExtractionResult
from app.core.vision import VisionAnnotation, VisionError, VisionNotConfiguredError
from tests.conftest import TenantFixture, login
from tests.test_evidence_api import _PNG_BYTES, _TXT_BYTES, _upload, storage_root  # noqa: F401


def _stub_vision(monkeypatch, *, text: str, confidence: float, pages: int = 1) -> None:
    """Substitui as chamadas à Vision API por uma anotação fixa.

    Mantém a suíte offline e determinística: o que se testa aqui é o roteamento,
    a marcação de confiança e a persistência — não a acurácia do OCR do Google.
    """
    annotation = VisionAnnotation(text=text, confidence=confidence, pages_annotated=pages)

    async def _annotate_image(content: bytes) -> VisionAnnotation:
        return annotation

    async def _annotate_pdf(content: bytes, *, max_pages: int) -> VisionAnnotation:
        return annotation

    monkeypatch.setattr(extraction, "annotate_image", _annotate_image)
    monkeypatch.setattr(extraction, "annotate_pdf", _annotate_pdf)


def _make_pdf(stream: bytes) -> bytes:
    """Monta um PDF mínimo válido (xref correta) com `stream` como conteúdo."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _make_native_text_pdf(text: str = "Comprovante PIX 123") -> bytes:
    """PDF com `text` na camada nativa — pypdf extrai sem passar por OCR."""
    return _make_pdf(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())


def _make_scanned_pdf() -> bytes:
    """PDF válido cuja página não tem operador de texto — simula um escaneado.

    O conteúdo desenha um retângulo, então pypdf devolve string vazia: é
    exatamente o gatilho de roteamento para o OCR gerenciado em `extract_pdf`.
    """
    return _make_pdf(b"0.9 g 72 600 200 100 re f")


_PDF_TEXT = _make_native_text_pdf()
_PDF_SCANNED = _make_scanned_pdf()


async def _get_extractions(
    api_client: AsyncClient, headers: dict[str, str], case_id, evidence_id: str
) -> list[dict]:
    response = await api_client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/extractions", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_txt_upload_is_extracted_and_marked_processed(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    status_code, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="conversa.txt",
        content=_TXT_BYTES,
        mime_type="text/plain",
    )
    assert status_code == 201, body

    detail = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}",
        headers=auth_headers,
    )
    assert detail.json()["status"] == "processed"

    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert len(extractions) == 1
    run = extractions[0]
    assert run["outcome"] == "succeeded"
    assert run["kind"] == "plain_text"
    assert "golpe" in run["extracted_text"]
    assert run["confidence"] == 1.0
    assert run["limitations"]  # derivado sempre declara seus limites


async def test_native_pdf_text_is_extracted_without_ocr(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="comprovante.pdf",
        content=_PDF_TEXT,
        mime_type="application/pdf",
    )
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert len(extractions) == 1
    run = extractions[0]
    assert run["outcome"] == "succeeded"
    assert run["kind"] == "pdf_text"  # PDF com camada de texto não passa por OCR
    assert "Comprovante PIX 123" in run["extracted_text"]
    assert run["output_sha256"] is not None


async def test_image_upload_goes_through_managed_ocr(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
    monkeypatch,
) -> None:
    _stub_vision(monkeypatch, text="PIX enviado R$ 2.500,00", confidence=0.94)
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="print.png",
        content=_PNG_BYTES,
        mime_type="image/png",
    )
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert len(extractions) == 1
    run = extractions[0]
    assert run["outcome"] == "succeeded"
    assert run["kind"] == "image_vision_ocr"
    assert run["tool_name"] == "google-cloud-vision"
    assert run["extracted_text"] == "PIX enviado R$ 2.500,00"
    assert run["confidence"] == 0.94
    assert run["low_confidence"] is False
    assert "OCR" in run["limitations"]  # nunca apresentado como prova perfeita


async def test_scanned_pdf_falls_back_to_managed_ocr(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
    monkeypatch,
) -> None:
    _stub_vision(monkeypatch, text="BOLETIM DE OCORRENCIA", confidence=0.88)
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="bo.pdf",
        content=_PDF_SCANNED,
        mime_type="application/pdf",
    )
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    run = extractions[0]
    assert run["outcome"] == "succeeded"
    assert run["kind"] == "pdf_vision_ocr"  # sem camada de texto -> OCR
    assert run["extracted_text"] == "BOLETIM DE OCORRENCIA"
    assert run["low_confidence"] is False


async def test_low_confidence_ocr_is_flagged_for_human_review(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
    monkeypatch,
) -> None:
    # Abaixo do patamar (0.75): a leitura é gravada, marcada como insuficiente
    # e devolvida para conferência humana — nunca reprocessada por IA.
    _stub_vision(monkeypatch, text="P1X env1ado R\\$ 2.5OO,OO", confidence=0.41)
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="print-borrado.png",
        content=_PNG_BYTES,
        mime_type="image/png",
    )
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    run = extractions[0]
    # Confiança baixa não é falha: o texto derivado é preservado, só sinalizado.
    assert run["outcome"] == "succeeded"
    assert run["extracted_text"]
    assert run["low_confidence"] is True
    assert "insuficiente" in run["limitations"]


async def test_missing_vision_api_key_fails_explicitly(monkeypatch) -> None:
    # Sem chave configurada, o OCR falha de forma rastreável — nunca cai
    # silenciosamente para um extrator local (mesmo princípio de
    # LLMNotConfiguredError em orchestrator/llm.py).
    from app.core import vision

    monkeypatch.setattr(vision.settings, "google_vision_api_key", None)
    with pytest.raises(VisionNotConfiguredError):
        await vision.annotate_image(_PNG_BYTES)


async def test_vision_failure_surfaces_as_extraction_error(monkeypatch) -> None:
    async def _boom(content: bytes) -> VisionAnnotation:
        raise VisionError("Vision API respondeu 429: cota excedida")

    monkeypatch.setattr(extraction, "annotate_image", _boom)
    with pytest.raises(ExtractionError, match="cota excedida"):
        await extraction.extract_image(_PNG_BYTES)


async def test_corrupt_pdf_fails_without_touching_original(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    corrupt = b"%PDF-1.4 nada disso e um pdf de verdade"
    status_code, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="quebrado.pdf",
        content=corrupt,
        mime_type="application/pdf",
    )
    assert status_code == 201  # o upload em si é válido (magic bytes conferem)

    detail = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}",
        headers=auth_headers,
    )
    assert detail.json()["status"] == "failed"

    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert extractions[0]["outcome"] == "failed"
    assert extractions[0]["extracted_text"] is None
    assert extractions[0]["error_message"]

    # Falha de pipeline nunca apaga nem corrompe o original (roadmap 3.2).
    original = (
        storage_root
        / str(tenant_with_case.tenant_id)
        / str(tenant_with_case.case_id)
        / body["id"]
        / "original.pdf"
    )
    assert original.read_bytes() == corrupt


async def test_ocr_failure_marks_evidence_failed(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
    monkeypatch,
) -> None:
    async def _boom(mime_type: str, content: bytes) -> ExtractionResult:
        raise ExtractionError("OCR de imagem falhou: simulado")

    monkeypatch.setattr(extraction_service, "extract_content", _boom)
    _, body = await _upload(api_client, auth_headers, tenant_with_case.case_id)

    detail = await api_client.get(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}",
        headers=auth_headers,
    )
    assert detail.json()["status"] == "failed"
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert extractions[0]["outcome"] == "failed"
    assert "simulado" in extractions[0]["error_message"]


async def test_reprocess_creates_new_extraction_run(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="conversa.txt",
        content=_TXT_BYTES,
        mime_type="text/plain",
    )
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}/process",
        headers=auth_headers,
    )
    assert response.status_code == 202

    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    # Reprocessar cria uma execução nova — a anterior permanece intacta.
    assert len(extractions) == 2
    assert {run["outcome"] for run in extractions} == {"succeeded"}


async def test_extractions_are_tenant_isolated(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    other_tenant: TenantFixture,
    storage_root: Path,  # noqa: F811
) -> None:
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="conversa.txt",
        content=_TXT_BYTES,
        mime_type="text/plain",
    )
    other_headers = await login(api_client, other_tenant)
    base = f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}"
    for method, url in (
        ("GET", f"{base}/extractions"),
        ("POST", f"{base}/process"),
    ):
        response = await api_client.request(method, url, headers=other_headers)
        assert response.status_code == 404, url


async def test_human_review_is_recorded_without_replacing_text(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    _, body = await _upload(
        api_client,
        auth_headers,
        tenant_with_case.case_id,
        filename="conversa.txt",
        content=_TXT_BYTES,
        mime_type="text/plain",
    )
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    extraction_id = extractions[0]["id"]
    original_text = extractions[0]["extracted_text"]

    base = f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}"
    response = await api_client.post(
        f"{base}/extractions/{extraction_id}/review",
        json={"verdict": "extraction_error", "note": "Faltou a última linha da conversa."},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["verdict"] == "extraction_error"
    assert review["note"] == "Faltou a última linha da conversa."

    # A correção é um registro — o texto derivado permanece intacto.
    extractions = await _get_extractions(
        api_client, auth_headers, tenant_with_case.case_id, body["id"]
    )
    assert extractions[0]["extracted_text"] == original_text
    assert extractions[0]["reviews"][0]["verdict"] == "extraction_error"


async def test_review_missing_extraction_returns_404(
    api_client: AsyncClient,
    tenant_with_case: TenantFixture,
    auth_headers: dict[str, str],
    storage_root: Path,  # noqa: F811
) -> None:
    _, body = await _upload(api_client, auth_headers, tenant_with_case.case_id)
    response = await api_client.post(
        f"/api/v1/cases/{tenant_with_case.case_id}/evidence/{body['id']}"
        f"/extractions/{uuid.uuid4()}/review",
        json={"verdict": "confirmed"},
        headers=auth_headers,
    )
    assert response.status_code == 404
