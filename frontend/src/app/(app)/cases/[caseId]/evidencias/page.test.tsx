import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, EvidenceAnalysisResult, EvidenceFile, User } from "@/types/api";

import CaseEvidenciasPage from "./page";

const {
  getCaseMock,
  listEvidenceMock,
  uploadEvidenceMock,
  processEvidenceMock,
  downloadEvidenceMock,
  getEvidenceAnalysisMock,
  runEvidenceAnalysisMock,
  reviewEvidenceAnalysisMock,
  listCaseDocumentsMock,
} = vi.hoisted(() => ({
  getCaseMock: vi.fn(),
  listEvidenceMock: vi.fn(),
  uploadEvidenceMock: vi.fn(),
  processEvidenceMock: vi.fn(),
  downloadEvidenceMock: vi.fn(),
  getEvidenceAnalysisMock: vi.fn(),
  runEvidenceAnalysisMock: vi.fn(),
  reviewEvidenceAnalysisMock: vi.fn(),
  listCaseDocumentsMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getCase: getCaseMock,
      listEvidence: listEvidenceMock,
      uploadEvidence: uploadEvidenceMock,
      processEvidence: processEvidenceMock,
      downloadEvidence: downloadEvidenceMock,
      getEvidenceAnalysis: getEvidenceAnalysisMock,
      runEvidenceAnalysis: runEvidenceAnalysisMock,
      reviewEvidenceAnalysis: reviewEvidenceAnalysisMock,
      listCaseDocuments: listCaseDocumentsMock,
    },
  };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "55555555-5555-5555-5555-555555555555" }),
}));

const useAuthMock = vi.fn();
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => useAuthMock() }));

const CASE_ID = "55555555-5555-5555-5555-555555555555";

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

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: CASE_ID,
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: null,
    area: "digital",
    matter: "Fraude em marketplace",
    platform: "facebook_marketplace",
    fraud_type: "marketplace",
    urgency: "high",
    status: "in_progress",
    current_module: "evidence",
    human_review_required: false,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}

function makeEvidence(overrides: Partial<EvidenceFile> = {}): EvidenceFile {
  return {
    id: "evidence-1",
    tenant_id: "tenant-1",
    case_id: CASE_ID,
    uploaded_by: "user-1",
    original_filename: "print-conversa.png",
    mime_type: "image/png",
    extension: "png",
    size_bytes: 2048,
    sha256_hash: "a".repeat(64),
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

function makeAnalysis(overrides: Partial<EvidenceAnalysisResult> = {}): EvidenceAnalysisResult {
  return {
    case_id: CASE_ID,
    evidence_outcome: "awaiting_human_review",
    findings: [
      {
        id: "finding-1",
        evidence_id: "evidence-1",
        agent: "documental",
        category: "fact",
        evidence_type: "conversation",
        summary: "Cliente foi induzido a transferir via PIX.",
        relevance: "high",
        suggested_use: "Narrativa dos fatos.",
        gaps: [],
        confidence: 0.85,
        status: "DRAFT_PENDING_REVIEW",
        created_at: "2026-07-10T12:05:00Z",
      },
      {
        id: "finding-2",
        evidence_id: null,
        agent: "documental",
        category: "missing_info",
        evidence_type: "document",
        summary: "Falta o comprovante PIX.",
        relevance: "high",
        suggested_use: "Solicitar ao cliente.",
        gaps: ["comprovante PIX"],
        confidence: 1,
        status: "DRAFT_PENDING_REVIEW",
        created_at: "2026-07-10T12:05:00Z",
      },
    ],
    specialist_assessment: {
      platform_context: "Marketplace intermedia a transação.",
      platform_failure: null,
      report_mechanism_analysis: null,
      preservation_recommendations: [],
      hypotheses: [],
      status: "DRAFT_PENDING_REVIEW",
    },
    documents_requested: ["Comprovante PIX"],
    human_review_required: true,
    status: "pending_approval",
    current_module: "evidence",
    ...overrides,
  };
}

function makeTxtFile(name = "conversa.txt"): File {
  return new File(["cliente: fui vitima de golpe"], name, { type: "text/plain" });
}

beforeEach(() => {
  for (const mock of [
    getCaseMock,
    listEvidenceMock,
    uploadEvidenceMock,
    processEvidenceMock,
    downloadEvidenceMock,
    getEvidenceAnalysisMock,
    runEvidenceAnalysisMock,
    reviewEvidenceAnalysisMock,
    listCaseDocumentsMock,
  ]) {
    mock.mockReset();
  }
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });

  getCaseMock.mockResolvedValue(makeCase());
  listEvidenceMock.mockResolvedValue([makeEvidence()]);
  getEvidenceAnalysisMock.mockResolvedValue(makeAnalysis());
  listCaseDocumentsMock.mockResolvedValue([]);
});

describe("CaseEvidenciasPage — estados de carregamento e acesso", () => {
  it("mostra o estado de carregamento antes dos dados chegarem", async () => {
    let resolveEvidence: (value: EvidenceFile[]) => void = () => {};
    listEvidenceMock.mockReturnValue(
      new Promise<EvidenceFile[]>((resolve) => (resolveEvidence = resolve)),
    );

    render(<CaseEvidenciasPage />);
    expect(screen.getByText("Carregando evidências...")).toBeInTheDocument();

    resolveEvidence([makeEvidence()]);
    await waitFor(() => expect(screen.getByText("Enviar evidências")).toBeInTheDocument());
  });

  it("mostra acesso negado quando o backend responde 403", async () => {
    listEvidenceMock.mockRejectedValue(new ApiError(403, "Sem permissão."));

    render(<CaseEvidenciasPage />);
    await waitFor(() =>
      expect(screen.getByText(/não tem acesso|Acesso negado/i)).toBeInTheDocument(),
    );
  });

  it("mostra erro recuperável quando a listagem falha", async () => {
    listEvidenceMock.mockRejectedValue(new ApiError(500, "Erro interno."));

    render(<CaseEvidenciasPage />);
    await waitFor(() => expect(screen.getByText("Erro interno.")).toBeInTheDocument());
  });

  it("mostra o estado vazio quando não há evidências", async () => {
    listEvidenceMock.mockResolvedValue([]);
    getEvidenceAnalysisMock.mockRejectedValue(new ApiError(404, "Ainda não executada."));

    render(<CaseEvidenciasPage />);
    await waitFor(() =>
      expect(screen.getByText("Nenhuma evidência anexada ainda")).toBeInTheDocument(),
    );
    expect(
      screen.getByText("A análise de evidências ainda não foi executada"),
    ).toBeInTheDocument();
  });
});

describe("CaseEvidenciasPage — inventário", () => {
  it("mostra status real de processamento e indicador de duplicidade", async () => {
    listEvidenceMock.mockResolvedValue([
      makeEvidence({ id: "e1", status: "processing", original_filename: "em-ocr.png" }),
      makeEvidence({
        id: "e2",
        status: "failed",
        original_filename: "quebrado.pdf",
        is_duplicate: true,
      }),
    ]);

    render(<CaseEvidenciasPage />);
    await waitFor(() => expect(screen.getByText("em-ocr.png")).toBeInTheDocument());
    expect(screen.getByText("Processando")).toBeInTheDocument();
    expect(screen.getByText("Falhou")).toBeInTheDocument();
    expect(screen.getByText("Duplicado")).toBeInTheDocument();
  });
});

describe("CaseEvidenciasPage — upload", () => {
  it("envia o arquivo e mostra a confirmação com status pendente de processamento", async () => {
    uploadEvidenceMock.mockResolvedValue(makeEvidence({ status: "received" }));
    const user = userEvent.setup();

    render(<CaseEvidenciasPage />);
    await waitFor(() => expect(screen.getByLabelText(/Anexar evidências/)).toBeInTheDocument());

    await user.upload(screen.getByLabelText(/Anexar evidências/), makeTxtFile());

    await waitFor(() =>
      expect(uploadEvidenceMock).toHaveBeenCalledWith(CASE_ID, expect.any(File)),
    );
    expect(
      await screen.findByText(/enviado e aguardando processamento/),
    ).toBeInTheDocument();
  });

  it("rejeita tipo não suportado sem chamar a API (espelho da validação do backend)", async () => {
    // applyAccept: false — sem isso o userEvent respeita o `accept` do input
    // e nem dispara o change; o teste quer exercitar a validação local.
    const user = userEvent.setup({ applyAccept: false });
    render(<CaseEvidenciasPage />);
    await waitFor(() => expect(screen.getByLabelText(/Anexar evidências/)).toBeInTheDocument());

    const zipFile = new File(["zip"], "arquivos.zip", { type: "application/zip" });
    await user.upload(screen.getByLabelText(/Anexar evidências/), zipFile);

    expect(await screen.findByText(/tipo de arquivo não suportado/)).toBeInTheDocument();
    expect(uploadEvidenceMock).not.toHaveBeenCalled();
  });

  it("mostra a mensagem de erro do backend quando o upload falha", async () => {
    uploadEvidenceMock.mockRejectedValue(
      new ApiError(422, "O conteúdo do arquivo não corresponde ao tipo declarado."),
    );
    const user = userEvent.setup();

    render(<CaseEvidenciasPage />);
    await waitFor(() => expect(screen.getByLabelText(/Anexar evidências/)).toBeInTheDocument());
    await user.upload(screen.getByLabelText(/Anexar evidências/), makeTxtFile());

    expect(
      await screen.findByText(/não corresponde ao tipo declarado/),
    ).toBeInTheDocument();
  });

  it("não mostra a área de upload para papel viewer", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });

    render(<CaseEvidenciasPage />);
    await waitFor(() =>
      expect(screen.getByText(/apenas consultar o inventário/)).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText(/Anexar evidências/)).not.toBeInTheDocument();
  });
});

describe("CaseEvidenciasPage — inventário probatório e revisão humana", () => {
  it("mostra achados com categorias distintas e o aviso de revisão humana", async () => {
    render(<CaseEvidenciasPage />);

    await waitFor(() =>
      expect(screen.getByText("Cliente foi induzido a transferir via PIX.")).toBeInTheDocument(),
    );
    expect(screen.getByText("Fato extraído")).toBeInTheDocument();
    expect(screen.getByText("Informação pendente")).toBeInTheDocument();
    expect(screen.getByText(/Revisão humana obrigatória/)).toBeInTheDocument();
  });

  it("aprovar exige confirmação e chama a API de revisão", async () => {
    reviewEvidenceAnalysisMock.mockResolvedValue(
      makeAnalysis({ current_module: "research", human_review_required: false }),
    );
    const user = userEvent.setup();

    render(<CaseEvidenciasPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Aprovar inventário" })).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Aprovar inventário" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aprovar e avançar" }));
    await waitFor(() =>
      expect(reviewEvidenceAnalysisMock).toHaveBeenCalledWith(CASE_ID, {
        decision: "approve",
        notes: undefined,
      }),
    );
  });

  it("devolver exige justificativa antes de enviar", async () => {
    reviewEvidenceAnalysisMock.mockResolvedValue(makeAnalysis());
    const user = userEvent.setup();

    render(<CaseEvidenciasPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Devolver para complementação" }),
      ).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Devolver para complementação" }));
    const submit = screen.getByRole("button", { name: "Confirmar devolução" });
    expect(submit).toBeDisabled();

    await user.type(
      screen.getByLabelText(/Justificativa/),
      "Falta o comprovante PIX do cliente.",
    );
    await user.click(screen.getByRole("button", { name: "Confirmar devolução" }));

    await waitFor(() =>
      expect(reviewEvidenceAnalysisMock).toHaveBeenCalledWith(CASE_ID, {
        decision: "return_for_information",
        notes: "Falta o comprovante PIX do cliente.",
      }),
    );
  });
});
