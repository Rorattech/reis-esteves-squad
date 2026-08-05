import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, CaseIntake, IntakeResult, User } from "@/types/api";

import CaseIntakePage from "./page";

const {
  getCaseMock,
  getCaseIntakeMock,
  updateCaseMock,
  submitCaseIntakeMock,
  runIntakeMock,
  getIntakeResultMock,
  reviewIntakeMock,
  listCaseDocumentsMock,
  getAuditLogMock,
  advanceCaseStageMock,
} = vi.hoisted(() => ({
  getCaseMock: vi.fn(),
  getCaseIntakeMock: vi.fn(),
  updateCaseMock: vi.fn(),
  submitCaseIntakeMock: vi.fn(),
  runIntakeMock: vi.fn(),
  getIntakeResultMock: vi.fn(),
  reviewIntakeMock: vi.fn(),
  listCaseDocumentsMock: vi.fn(),
  getAuditLogMock: vi.fn(),
  advanceCaseStageMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getCase: getCaseMock,
      getCaseIntake: getCaseIntakeMock,
      updateCase: updateCaseMock,
      submitCaseIntake: submitCaseIntakeMock,
      runIntake: runIntakeMock,
      getIntakeResult: getIntakeResultMock,
      reviewIntake: reviewIntakeMock,
      listCaseDocuments: listCaseDocumentsMock,
      getAuditLog: getAuditLogMock,
      advanceCaseStage: advanceCaseStageMock,
    },
  };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "55555555-5555-5555-5555-555555555555" }),
}));

const useAuthMock = vi.fn();
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => useAuthMock() }));

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "55555555-5555-5555-5555-555555555555",
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: null,
    area: null,
    matter: null,
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    status: "pending_approval",
    current_module: "intake",
    human_review_required: true,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}

function makeIntake(overrides: Partial<CaseIntake> = {}): CaseIntake {
  return {
    id: "intake-1",
    tenant_id: "tenant-1",
    case_id: "55555555-5555-5555-5555-555555555555",
    submitted_by: "user-1",
    narrative: "Recebi mensagem de contato clonado pedindo PIX urgente.",
    estimated_loss_amount: "3000.00",
    incident_date: "2026-06-30",
    has_police_report: false,
    claimed_documents: ["comprovante_pix.png"],
    pending_information: [],
    created_at: "2026-07-01T10:05:00Z",
    updated_at: "2026-07-01T10:05:00Z",
    ...overrides,
  };
}

function makeResult(overrides: Partial<IntakeResult> = {}): IntakeResult {
  return {
    case_id: "55555555-5555-5555-5555-555555555555",
    intake_outcome: "awaiting_human_review",
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    area: "digital",
    matter: "golpe do PIX via WhatsApp clonado",
    documents_requested: ["boletim_de_ocorrencia"],
    missing_information: [],
    out_of_scope_reason: null,
    human_review_required: true,
    status: "pending_approval",
    current_module: "intake",
    ...overrides,
  };
}

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

beforeEach(() => {
  for (const mock of [
    getCaseMock,
    getCaseIntakeMock,
    updateCaseMock,
    submitCaseIntakeMock,
    runIntakeMock,
    getIntakeResultMock,
    reviewIntakeMock,
    listCaseDocumentsMock,
    getAuditLogMock,
    advanceCaseStageMock,
  ]) {
    mock.mockReset();
  }
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });

  // Padrão "feliz": relato já enviado, triagem já rodou, aguardando revisão.
  getCaseMock.mockResolvedValue(makeCase());
  getCaseIntakeMock.mockResolvedValue(makeIntake());
  getIntakeResultMock.mockResolvedValue(makeResult());
  listCaseDocumentsMock.mockResolvedValue([]);
  getAuditLogMock.mockResolvedValue([]);
});

describe("CaseIntakePage — carregamento", () => {
  it("mostra o estado de carregamento antes dos dados chegarem", async () => {
    let resolveCase: (value: Case) => void = () => {};
    getCaseMock.mockReturnValue(new Promise<Case>((resolve) => (resolveCase = resolve)));

    render(<CaseIntakePage />);

    expect(screen.getByText("Carregando intake...")).toBeInTheDocument();

    resolveCase(makeCase());
    await waitFor(() => expect(screen.getByText("Relato inicial")).toBeInTheDocument());
  });

  it("mostra o painel de resultado, o relato e o histórico depois de carregado", async () => {
    render(<CaseIntakePage />);

    await waitFor(() => expect(screen.getByText("Aguardando revisão humana")).toBeInTheDocument());
    expect(screen.getByDisplayValue(/contato clonado pedindo PIX/)).toBeInTheDocument();
    expect(screen.getByText("golpe do PIX via WhatsApp clonado", { exact: false })).toBeInTheDocument();
  });
});

describe("CaseIntakePage — falha", () => {
  it("mostra erro com opção de tentar novamente quando o caso falha ao carregar", async () => {
    getCaseMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    render(<CaseIntakePage />);

    expect(await screen.findByText("Erro inesperado (HTTP 500).")).toBeInTheDocument();
  });

  it("mostra acesso negado quando o caso não existe para o tenant", async () => {
    getCaseMock.mockRejectedValue(new ApiError(404, "Caso não encontrado."));

    render(<CaseIntakePage />);

    expect(
      await screen.findByText("Este caso não existe ou você não tem acesso a ele."),
    ).toBeInTheDocument();
  });

  it("mostra erro ao executar a triagem sem interromper a tela", async () => {
    runIntakeMock.mockRejectedValue(new ApiError(503, "Provedor de IA ainda não configurado neste ambiente."));

    render(<CaseIntakePage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Executar triagem" })).toBeEnabled());

    await userEvent.click(screen.getByRole("button", { name: "Executar triagem" }));
    await userEvent.click(screen.getByRole("button", { name: "Executar" }));

    expect(
      await screen.findByText("Provedor de IA ainda não configurado neste ambiente."),
    ).toBeInTheDocument();
  });
});

describe("CaseIntakePage — Executar triagem", () => {
  it("fica desabilitado sem relato inicial e pede confirmação quando habilitado", async () => {
    getCaseIntakeMock.mockRejectedValue(new ApiError(404, "Relato inicial ainda não foi registrado."));
    getIntakeResultMock.mockRejectedValue(new ApiError(404, "O Intake ainda não foi executado."));

    render(<CaseIntakePage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Executar triagem" })).toBeDisabled(),
    );
    expect(runIntakeMock).not.toHaveBeenCalled();
  });

  it("executa a triagem só após confirmação e bloqueia clique duplicado", async () => {
    let resolveRun: (value: IntakeResult) => void = () => {};
    runIntakeMock.mockReturnValue(new Promise<IntakeResult>((resolve) => (resolveRun = resolve)));

    render(<CaseIntakePage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Executar triagem" })).toBeEnabled());

    await userEvent.click(screen.getByRole("button", { name: "Executar triagem" }));
    expect(runIntakeMock).not.toHaveBeenCalled(); // só depois de confirmar

    await userEvent.click(screen.getByRole("button", { name: "Executar" }));
    expect(runIntakeMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Executando triagem..." })).toBeDisabled();

    resolveRun(makeResult());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Executar triagem" })).toBeEnabled(),
    );
  });
});

describe("CaseIntakePage — revisão humana", () => {
  it("aprova a recomendação após confirmação", async () => {
    reviewIntakeMock.mockResolvedValue(makeCase({ status: "in_progress", current_module: "evidence" }));

    render(<CaseIntakePage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Aprovar" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Aprovar" }));
    // Abrir o ConfirmDialog cria um segundo botão "Aprovar" (o de confirmação).
    await userEvent.click(screen.getAllByRole("button", { name: "Aprovar" }).at(-1)!);

    await waitFor(() =>
      expect(reviewIntakeMock).toHaveBeenCalledWith("55555555-5555-5555-5555-555555555555", {
        decision: "approve",
      }),
    );
  });

  it("corrige a recomendação com justificativa obrigatória", async () => {
    reviewIntakeMock.mockResolvedValue(makeCase({ status: "in_progress", current_module: "evidence" }));

    render(<CaseIntakePage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Corrigir" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Corrigir" }));

    await userEvent.click(screen.getByRole("button", { name: "Confirmar correção" }));
    expect(
      await screen.findByText("Justificativa obrigatória para corrigir ou devolver."),
    ).toBeInTheDocument();
    expect(reviewIntakeMock).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByLabelText("Justificativa da correção"),
      "Plataforma correta é Mercado Livre, não WhatsApp.",
    );
    await userEvent.clear(screen.getByLabelText("Plataforma"));
    await userEvent.type(screen.getByLabelText("Plataforma"), "Mercado Livre");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar correção" }));

    await waitFor(() =>
      expect(reviewIntakeMock).toHaveBeenCalledWith("55555555-5555-5555-5555-555555555555", {
        decision: "correct",
        notes: "Plataforma correta é Mercado Livre, não WhatsApp.",
        platform: "Mercado Livre",
        fraud_type: "pix",
        urgency: "high",
        area: "digital",
        matter: "golpe do PIX via WhatsApp clonado",
      }),
    );
  });

  it("devolve o caso para complementação com justificativa obrigatória", async () => {
    reviewIntakeMock.mockResolvedValue(makeCase({ status: "in_progress" }));

    render(<CaseIntakePage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Devolver para complementação" })).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Devolver para complementação" }));

    await userEvent.click(screen.getByRole("button", { name: "Confirmar devolução" }));
    expect(
      await screen.findByText("Justificativa obrigatória para corrigir ou devolver."),
    ).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText("O que falta para complementar o caso?"),
      "Falta o valor exato do golpe.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirmar devolução" }));

    await waitFor(() =>
      expect(reviewIntakeMock).toHaveBeenCalledWith("55555555-5555-5555-5555-555555555555", {
        decision: "return_for_information",
        notes: "Falta o valor exato do golpe.",
      }),
    );
  });

  it("não permite revisão quando o caso não está aguardando aprovação", async () => {
    getCaseMock.mockResolvedValue(makeCase({ status: "in_progress" }));

    render(<CaseIntakePage />);

    expect(
      await screen.findByText("Não há nenhuma recomendação de triagem pendente de revisão no momento."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprovar" })).not.toBeInTheDocument();
  });

  it("mostra erro da API sem fingir sucesso quando a aprovação falha", async () => {
    reviewIntakeMock.mockRejectedValue(new ApiError(409, "Este caso não tem nenhuma recomendação de Intake pendente de revisão."));

    render(<CaseIntakePage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Aprovar" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Aprovar" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Aprovar" }).at(-1)!);

    expect(
      await screen.findByText("Este caso não tem nenhuma recomendação de Intake pendente de revisão."),
    ).toBeInTheDocument();
  });
});

describe("CaseIntakePage — avanço da abertura para Evidências", () => {
  /**
   * Sem provedor de IA configurado a triagem responde 503, o caso nunca chega
   * a `pending_approval` e o fluxo de aprovação fica sem nada para aprovar —
   * este é o único caminho para o caso sair da abertura.
   */
  function caseWithoutRecommendation() {
    getCaseMock.mockResolvedValue(makeCase({ status: "draft" }));
    getIntakeResultMock.mockRejectedValue(new ApiError(404, "O Intake ainda não foi executado."));
  }

  it("avança o caso e recarrega os dados a partir do backend", async () => {
    caseWithoutRecommendation();
    advanceCaseStageMock.mockResolvedValue(makeCase({ current_module: "evidence" }));

    render(<CaseIntakePage />);
    const advanceButton = await screen.findByRole("button", { name: /Avançar para Evidências/ });

    await userEvent.type(
      screen.getByLabelText(/Observação para o histórico/),
      "Documentos conferidos.",
    );
    await userEvent.click(advanceButton);

    // Ação que muda a etapa do caso: exige confirmação explícita.
    expect(advanceCaseStageMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Avançar" }));

    await waitFor(() =>
      expect(advanceCaseStageMock).toHaveBeenCalledWith("55555555-5555-5555-5555-555555555555", {
        notes: "Documentos conferidos.",
      }),
    );
    // A etapa vem do backend recarregado, nunca de atualização otimista.
    await waitFor(() => expect(getCaseMock).toHaveBeenCalledTimes(2));
  });

  it("bloqueia o avanço enquanto não houver relato inicial", async () => {
    caseWithoutRecommendation();
    getCaseIntakeMock.mockRejectedValue(new ApiError(404, "Relato inicial ainda não registrado."));

    render(<CaseIntakePage />);

    const advanceButton = await screen.findByRole("button", { name: /Avançar para Evidências/ });
    expect(advanceButton).toBeDisabled();
    expect(
      screen.getByText("Salve o relato inicial antes de avançar o caso para Evidências."),
    ).toBeInTheDocument();
  });

  it("mostra o erro do backend sem marcar o caso como avançado", async () => {
    caseWithoutRecommendation();
    advanceCaseStageMock.mockRejectedValue(
      new ApiError(409, "Este caso já saiu da abertura de caso."),
    );

    render(<CaseIntakePage />);
    await userEvent.click(await screen.findByRole("button", { name: /Avançar para Evidências/ }));
    await userEvent.click(screen.getByRole("button", { name: "Avançar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Este caso já saiu da abertura de caso.",
    );
  });

  it("não oferece o avanço manual quando há recomendação pendente de revisão", async () => {
    // Padrão do beforeEach: status pending_approval — o caminho correto é
    // aprovar/corrigir/devolver a recomendação, não avançar por fora dela.
    render(<CaseIntakePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Aprovar" })).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: /Avançar para Evidências/ }),
    ).not.toBeInTheDocument();
  });

  it("não oferece o avanço para o papel viewer", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });
    caseWithoutRecommendation();

    render(<CaseIntakePage />);

    await waitFor(() => expect(screen.getByText("Relato inicial")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: /Avançar para Evidências/ }),
    ).not.toBeInTheDocument();
  });

  it("não oferece o avanço quando o caso já está em Evidências", async () => {
    getCaseMock.mockResolvedValue(
      makeCase({ status: "in_progress", current_module: "evidence" }),
    );
    getIntakeResultMock.mockRejectedValue(new ApiError(404, "O Intake ainda não foi executado."));

    render(<CaseIntakePage />);

    await waitFor(() => expect(screen.getByText("Relato inicial")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: /Avançar para Evidências/ }),
    ).not.toBeInTheDocument();
  });
});
