import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { EvidenceExtraction, EvidenceFile, User } from "@/types/api";

import EvidenceDetailPage from "./page";

const {
  getEvidenceMock,
  listEvidenceExtractionsMock,
  downloadEvidenceMock,
  processEvidenceMock,
  reviewEvidenceExtractionMock,
  getEvidenceAnalysisMock,
} = vi.hoisted(() => ({
  getEvidenceMock: vi.fn(),
  listEvidenceExtractionsMock: vi.fn(),
  downloadEvidenceMock: vi.fn(),
  processEvidenceMock: vi.fn(),
  reviewEvidenceExtractionMock: vi.fn(),
  getEvidenceAnalysisMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getEvidence: getEvidenceMock,
      listEvidenceExtractions: listEvidenceExtractionsMock,
      downloadEvidence: downloadEvidenceMock,
      processEvidence: processEvidenceMock,
      reviewEvidenceExtraction: reviewEvidenceExtractionMock,
      getEvidenceAnalysis: getEvidenceAnalysisMock,
    },
  };
});

const CASE_ID = "55555555-5555-5555-5555-555555555555";
const EVIDENCE_ID = "66666666-6666-6666-6666-666666666666";

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: CASE_ID, evidenceId: EVIDENCE_ID }),
}));

const useAuthMock = vi.fn();
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => useAuthMock() }));

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    tenant_id: "tenant-1",
    tenant_name: "Reis Esteves",
    email: "advogada@reisesteves.com.br",
    role: "lawyer",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeEvidence(overrides: Partial<EvidenceFile> = {}): EvidenceFile {
  return {
    id: EVIDENCE_ID,
    tenant_id: "tenant-1",
    case_id: CASE_ID,
    uploaded_by: "user-1",
    original_filename: "conversa.txt",
    mime_type: "text/plain",
    extension: "txt",
    size_bytes: 512,
    sha256_hash: "b".repeat(64),
    origin: "upload_portal",
    status: "processed",
    duplicate_of_id: null,
    notes: null,
    created_at: "2026-07-10T12:00:00Z",
    updated_at: "2026-07-10T12:01:00Z",
    is_duplicate: false,
    ...overrides,
  };
}

function makeExtraction(overrides: Partial<EvidenceExtraction> = {}): EvidenceExtraction {
  return {
    id: "extraction-1",
    evidence_id: EVIDENCE_ID,
    kind: "plain_text",
    outcome: "succeeded",
    extracted_text: "cliente: fui vitima de golpe no marketplace",
    confidence: 1,
    low_confidence: false,
    limitations: "Decodificação direta de texto puro.",
    tool_name: "python-utf8",
    tool_version: "3",
    input_sha256: "b".repeat(64),
    output_sha256: "c".repeat(64),
    duration_ms: 12,
    error_message: null,
    created_at: "2026-07-10T12:02:00Z",
    reviews: [],
    ...overrides,
  };
}

beforeEach(() => {
  for (const mock of [
    getEvidenceMock,
    listEvidenceExtractionsMock,
    downloadEvidenceMock,
    processEvidenceMock,
    reviewEvidenceExtractionMock,
    getEvidenceAnalysisMock,
  ]) {
    mock.mockReset();
  }
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });

  getEvidenceMock.mockResolvedValue(makeEvidence());
  listEvidenceExtractionsMock.mockResolvedValue([makeExtraction()]);
  getEvidenceAnalysisMock.mockRejectedValue(new ApiError(404, "Ainda não executada."));
  downloadEvidenceMock.mockResolvedValue(new Blob(["conteudo"], { type: "text/plain" }));
});

describe("EvidenceDetailPage — visualização", () => {
  it("mostra metadados, hash de integridade e o texto extraído como conteúdo derivado", async () => {
    render(<EvidenceDetailPage />);

    await waitFor(() => expect(screen.getByText("conversa.txt")).toBeInTheDocument());
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
    expect(
      screen.getByText("cliente: fui vitima de golpe no marketplace"),
    ).toBeInTheDocument();
    // Separação explícita original × derivado (roadmap 3.5).
    expect(screen.getByText("Conteúdo derivado.")).toBeInTheDocument();
    expect(screen.getByText(/confiança 100%/)).toBeInTheDocument();
    expect(screen.getByText("Decodificação direta de texto puro.")).toBeInTheDocument();
  });

  it("mostra acesso negado quando a evidência não existe neste tenant", async () => {
    getEvidenceMock.mockRejectedValue(new ApiError(404, "Evidência não encontrada."));

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(screen.getByText(/não tem acesso|Acesso negado/i)).toBeInTheDocument(),
    );
  });

  it("mostra o estado vazio quando ainda não há extração", async () => {
    listEvidenceExtractionsMock.mockResolvedValue([]);

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(screen.getByText("Nenhuma extração registrada ainda")).toBeInTheDocument(),
    );
  });

  it("destaca conferência humana obrigatória quando o OCR ficou insuficiente", async () => {
    listEvidenceExtractionsMock.mockResolvedValue([
      makeExtraction({
        kind: "image_vision_ocr",
        tool_name: "google-cloud-vision",
        extracted_text: "P1X env1ado R$ 2.5OO,OO",
        confidence: 0.41,
        low_confidence: true,
        limitations: "Texto obtido por OCR — conteúdo derivado, sujeito a erros de leitura.",
      }),
    ]);

    render(<EvidenceDetailPage />);

    await waitFor(() =>
      expect(screen.getByText("Conferência humana obrigatória.")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Leitura insuficiente/)).toBeInTheDocument();
    // O texto derivado continua visível: baixa confiança sinaliza, não descarta.
    expect(screen.getByText("P1X env1ado R$ 2.5OO,OO")).toBeInTheDocument();
    // E a revisão humana continua disponível para apontar o erro.
    expect(
      screen.getByRole("button", { name: /Apontar erro de extração/ }),
    ).toBeInTheDocument();
  });

  it("mostra a falha de processamento sem perder o original", async () => {
    getEvidenceMock.mockResolvedValue(makeEvidence({ status: "failed" }));
    listEvidenceExtractionsMock.mockResolvedValue([
      makeExtraction({
        outcome: "failed",
        extracted_text: null,
        confidence: null,
        error_message: "PDF ilegível: PdfStreamError",
      }),
    ]);

    render(<EvidenceDetailPage />);
    await waitFor(() => expect(screen.getByText("Extração falhou")).toBeInTheDocument());
    expect(screen.getByText(/PDF ilegível/)).toBeInTheDocument();
    expect(screen.getByText(/arquivo original permanece\s+intacto/)).toBeInTheDocument();
    // O original continua acessível para download.
    expect(
      screen.getByRole("button", { name: /Baixar original/ }),
    ).toBeInTheDocument();
  });
});

describe("EvidenceDetailPage — validação humana da extração", () => {
  it("confirma o conteúdo extraído chamando a API de revisão", async () => {
    reviewEvidenceExtractionMock.mockResolvedValue({
      id: "review-1",
      extraction_id: "extraction-1",
      reviewer_id: "user-1",
      verdict: "confirmed",
      note: null,
      created_at: "2026-07-10T13:00:00Z",
    });
    const user = userEvent.setup();

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Confirmar conteúdo" })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Confirmar conteúdo" }));

    await waitFor(() =>
      expect(reviewEvidenceExtractionMock).toHaveBeenCalledWith(
        CASE_ID,
        EVIDENCE_ID,
        "extraction-1",
        { verdict: "confirmed", note: undefined },
      ),
    );
  });

  it("apontar erro exige observação e registra sem substituir o texto", async () => {
    reviewEvidenceExtractionMock.mockResolvedValue({
      id: "review-2",
      extraction_id: "extraction-1",
      reviewer_id: "user-1",
      verdict: "extraction_error",
      note: "Faltou a última linha.",
      created_at: "2026-07-10T13:00:00Z",
    });
    const user = userEvent.setup();

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Apontar erro de extração" }),
      ).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Apontar erro de extração" }));

    const submit = screen.getByRole("button", { name: "Registrar erro" });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/Descreva o erro/), "Faltou a última linha.");
    await user.click(screen.getByRole("button", { name: "Registrar erro" }));

    await waitFor(() =>
      expect(reviewEvidenceExtractionMock).toHaveBeenCalledWith(
        CASE_ID,
        EVIDENCE_ID,
        "extraction-1",
        { verdict: "extraction_error", note: "Faltou a última linha." },
      ),
    );
  });

  it("mostra revisões já registradas da extração", async () => {
    listEvidenceExtractionsMock.mockResolvedValue([
      makeExtraction({
        reviews: [
          {
            id: "review-1",
            extraction_id: "extraction-1",
            reviewer_id: "user-1",
            verdict: "extraction_error",
            note: "OCR trocou o valor do PIX.",
            created_at: "2026-07-10T13:00:00Z",
          },
        ],
      }),
    ]);

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(screen.getByText(/Erro de extração apontado/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/OCR trocou o valor do PIX./)).toBeInTheDocument();
    // O texto derivado continua visível, intacto.
    expect(
      screen.getByText("cliente: fui vitima de golpe no marketplace"),
    ).toBeInTheDocument();
  });

  it("papel viewer não vê ações de revisão nem o download do original", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });
    listEvidenceExtractionsMock.mockRejectedValue(new ApiError(403, "Sem permissão."));

    render(<EvidenceDetailPage />);
    await waitFor(() =>
      expect(
        screen.getByText(/não o conteúdo original do arquivo/),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/não tem acesso ao conteúdo extraído/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirmar conteúdo" })).not.toBeInTheDocument();
  });
});
