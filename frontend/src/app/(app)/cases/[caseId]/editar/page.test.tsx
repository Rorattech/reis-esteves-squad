import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, User } from "@/types/api";

import EditCasePage from "./page";

const { getCaseMock, updateCaseMock, pushMock } = vi.hoisted(() => ({
  getCaseMock: vi.fn(),
  updateCaseMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, getCase: getCaseMock, updateCase: updateCaseMock } };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "66666666-6666-6666-6666-666666666666" }),
  useRouter: () => ({ push: pushMock }),
}));

const useAuthMock = vi.fn();
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => useAuthMock() }));

const CLIENT_TOKEN = "3f2a9c10-4b7e-4d51-9a2f-8e0c1d6b5a44";

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "66666666-6666-6666-6666-666666666666",
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: CLIENT_TOKEN,
    area: "digital",
    matter: "golpe do PIX via WhatsApp clonado",
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    status: "draft",
    current_module: "intake",
    human_review_required: true,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
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
  getCaseMock.mockReset();
  updateCaseMock.mockReset();
  pushMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
  getCaseMock.mockResolvedValue(makeCase());
});

describe("EditCasePage", () => {
  it("mostra o estado de carregamento antes dos dados chegarem", () => {
    getCaseMock.mockReturnValue(new Promise<Case>(() => {}));

    render(<EditCasePage />);

    expect(screen.getByText("Carregando caso...")).toBeInTheDocument();
  });

  it("carrega token do cliente, área e matéria já preenchidos", async () => {
    render(<EditCasePage />);

    await waitFor(() =>
      expect(screen.getByLabelText(/Token do cliente/)).toHaveValue(CLIENT_TOKEN),
    );
    expect(screen.getByLabelText(/^Área/)).toHaveValue("digital");
    expect(screen.getByLabelText(/Matéria/)).toHaveValue("golpe do PIX via WhatsApp clonado");
  });

  it("salva as alterações e volta para o caso", async () => {
    updateCaseMock.mockResolvedValue(makeCase({ matter: "estelionato digital" }));

    render(<EditCasePage />);
    await waitFor(() => expect(screen.getByLabelText(/Matéria/)).toBeInTheDocument());

    await userEvent.clear(screen.getByLabelText(/Matéria/));
    await userEvent.type(screen.getByLabelText(/Matéria/), "estelionato digital");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(updateCaseMock).toHaveBeenCalledWith("66666666-6666-6666-6666-666666666666", {
        platform: "whatsapp",
        fraud_type: "pix",
        urgency: "high",
        client_id: CLIENT_TOKEN,
        area: "digital",
        matter: "estelionato digital",
      }),
    );
    expect(pushMock).toHaveBeenCalledWith("/cases/66666666-6666-6666-6666-666666666666");
  });

  it("desvincula o cliente quando o token é apagado", async () => {
    updateCaseMock.mockResolvedValue(makeCase({ client_id: null }));

    render(<EditCasePage />);
    await waitFor(() => expect(screen.getByLabelText(/Token do cliente/)).toBeInTheDocument());

    await userEvent.clear(screen.getByLabelText(/Token do cliente/));
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(updateCaseMock.mock.calls[0][1]).toMatchObject({ client_id: null }),
    );
  });

  it("rejeita um token de cliente fora do formato esperado, sem chamar a API", async () => {
    render(<EditCasePage />);
    await waitFor(() => expect(screen.getByLabelText(/Token do cliente/)).toBeInTheDocument());

    await userEvent.clear(screen.getByLabelText(/Token do cliente/));
    await userEvent.type(screen.getByLabelText(/Token do cliente/), "cliente-123");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(
      await screen.findByText(
        "Token do cliente inválido — use o identificador completo do cliente.",
      ),
    ).toBeInTheDocument();
    expect(updateCaseMock).not.toHaveBeenCalled();
  });

  it("mostra a mensagem do backend e não redireciona quando o salvamento falha", async () => {
    updateCaseMock.mockRejectedValue(new ApiError(404, "Cliente não encontrado."));

    render(<EditCasePage />);
    await waitFor(() => expect(screen.getByLabelText(/Matéria/)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cliente não encontrado.");
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("nega o acesso ao papel viewer", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });

    render(<EditCasePage />);

    expect(
      await screen.findByText("Este caso não existe ou você não tem acesso a ele."),
    ).toBeInTheDocument();
  });

  it("mostra acesso negado quando o caso não existe para o tenant", async () => {
    getCaseMock.mockRejectedValue(new ApiError(404, "Caso não encontrado."));

    render(<EditCasePage />);

    expect(
      await screen.findByText("Este caso não existe ou você não tem acesso a ele."),
    ).toBeInTheDocument();
  });
});
