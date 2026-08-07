import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, User } from "@/types/api";

import EditCasePage from "./page";
import {
  makeCase as makeBaseCase,
  makeClientSummary,
  makeFraudModality,
  makePlatform,
} from "@/test/factories";

const SHOPEE = makePlatform({ id: "platform-2", slug: "shopee", label: "Shopee", sort_order: 60 });

/** Caso base destes testes — caso recém-aberto, ainda em rascunho. */
function makeCase(overrides: Partial<Case> = {}): Case {
  return makeBaseCase({
    // Mesmo id do parâmetro de rota mockado abaixo.
    id: "66666666-6666-6666-6666-666666666666",
    status: "draft",
    area: "digital",
    matter: "golpe do PIX via WhatsApp clonado",
    client_id: "client-1",
    client: makeClientSummary(),
    ...overrides,
  });
}

const {
  getCaseMock,
  updateCaseMock,
  listPlatformsMock,
  listFraudModalitiesMock,
  listClientsMock,
  pushMock,
} = vi.hoisted(() => ({
  getCaseMock: vi.fn(),
  updateCaseMock: vi.fn(),
  listPlatformsMock: vi.fn(),
  listFraudModalitiesMock: vi.fn(),
  listClientsMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getCase: getCaseMock,
      updateCase: updateCaseMock,
      listPlatforms: listPlatformsMock,
      listFraudModalities: listFraudModalitiesMock,
      listClients: listClientsMock,
    },
  };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "66666666-6666-6666-6666-666666666666" }),
  useRouter: () => ({ push: pushMock }),
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

beforeEach(() => {
  getCaseMock.mockReset();
  updateCaseMock.mockReset();
  pushMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
  getCaseMock.mockResolvedValue(makeCase());

  listPlatformsMock.mockReset();
  listFraudModalitiesMock.mockReset();
  listClientsMock.mockReset();
  listPlatformsMock.mockResolvedValue([makePlatform(), SHOPEE]);
  listFraudModalitiesMock.mockResolvedValue([makeFraudModality()]);
  listClientsMock.mockResolvedValue([]);
});

describe("EditCasePage", () => {
  it("mostra o estado de carregamento antes dos dados chegarem", () => {
    getCaseMock.mockReturnValue(new Promise<Case>(() => {}));

    render(<EditCasePage />);

    expect(screen.getByText("Carregando caso...")).toBeInTheDocument();
  });

  it("carrega classificação, cliente, área e matéria já preenchidos", async () => {
    render(<EditCasePage />);

    // Cliente aparece por nome e código — o UUID não é mais exibido nem digitado.
    expect(await screen.findByText("Maria Souza de Oliveira")).toBeInTheDocument();
    expect(screen.getByText("CLI-000001")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Token do cliente/)).not.toBeInTheDocument();

    expect(screen.getByLabelText("Plataforma envolvida")).toHaveValue("platform-1");
    expect(screen.getByLabelText("Modalidade do golpe")).toHaveValue("modality-1");
    expect(screen.getByLabelText(/^Área/)).toHaveValue("digital");
    expect(screen.getByLabelText(/Matéria/)).toHaveValue("golpe do PIX via WhatsApp clonado");
  });

  it("não permite editar o código do caso, que é emitido uma vez só", async () => {
    render(<EditCasePage />);
    await screen.findByLabelText(/Matéria/);

    expect(screen.queryByLabelText(/Código/)).not.toBeInTheDocument();
  });

  it("salva as alterações e volta para o caso", async () => {
    updateCaseMock.mockResolvedValue(makeCase({ matter: "estelionato digital" }));

    render(<EditCasePage />);
    await screen.findByLabelText(/Matéria/);

    await userEvent.selectOptions(screen.getByLabelText("Plataforma envolvida"), SHOPEE.id);
    await userEvent.clear(screen.getByLabelText(/Matéria/));
    await userEvent.type(screen.getByLabelText(/Matéria/), "estelionato digital");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(updateCaseMock).toHaveBeenCalledWith("66666666-6666-6666-6666-666666666666", {
        platform_id: SHOPEE.id,
        fraud_modality_id: "modality-1",
        urgency: "high",
        client_id: "client-1",
        area: "digital",
        matter: "estelionato digital",
      }),
    );
    expect(pushMock).toHaveBeenCalledWith("/cases/66666666-6666-6666-6666-666666666666");
  });

  it("desvincula o cliente sem apagar o cadastro dele", async () => {
    updateCaseMock.mockResolvedValue(makeCase({ client_id: null, client: null }));

    render(<EditCasePage />);
    await screen.findByText("Maria Souza de Oliveira");

    await userEvent.click(screen.getByRole("button", { name: "Trocar cliente" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(updateCaseMock.mock.calls[0][1]).toMatchObject({ client_id: null }),
    );
  });

  it("mostra a mensagem do backend e não redireciona quando o salvamento falha", async () => {
    updateCaseMock.mockRejectedValue(new ApiError(404, "Cliente não encontrado."));

    render(<EditCasePage />);
    await screen.findByLabelText(/Matéria/);

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
