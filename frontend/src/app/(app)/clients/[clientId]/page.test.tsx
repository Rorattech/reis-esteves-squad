import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import { makeCase, makeClient } from "@/test/factories";

import ClientDetailPage from "./page";

const { getClientMock, listCasesMock } = vi.hoisted(() => ({
  getClientMock: vi.fn(),
  listCasesMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: { ...actual.api, getClient: getClientMock, listCases: listCasesMock },
  };
});

vi.mock("next/navigation", () => ({ useParams: () => ({ clientId: "client-1" }) }));

function renderPage() {
  return render(<ClientDetailPage />);
}

beforeEach(() => {
  getClientMock.mockReset();
  listCasesMock.mockReset();
  listCasesMock.mockResolvedValue([]);
});

describe("ClientDetailPage", () => {
  it("mostra a qualificação completa do cliente", async () => {
    getClientMock.mockResolvedValue(makeClient());

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Maria Souza de Oliveira" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/CLI-000001/)).toBeInTheDocument();
    expect(screen.getByText("529.982.247-25")).toBeInTheDocument();
    expect(screen.getByText("01310-100")).toBeInTheDocument();
    expect(screen.getByText("São Paulo/SP")).toBeInTheDocument();
    expect(screen.getByText("Casado(a)")).toBeInTheDocument();
    expect(screen.getByText("professora")).toBeInTheDocument();
  });

  it("explica que o município é o que vai para os agentes", async () => {
    getClientMock.mockResolvedValue(makeClient());

    renderPage();

    expect(await screen.findByText(/foro do consumidor \(CDC art. 101, I\)/)).toBeInTheDocument();
  });

  it("lista os casos do cliente buscando pelo código dele", async () => {
    getClientMock.mockResolvedValue(makeClient());
    listCasesMock.mockResolvedValue([makeCase()]);

    renderPage();

    await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());
    expect(listCasesMock).toHaveBeenLastCalledWith({
      search: "CLI-000001",
      status: undefined,
    });
  });

  it("mostra o estado vazio quando o cliente ainda não tem caso", async () => {
    getClientMock.mockResolvedValue(makeClient());

    renderPage();

    expect(
      await screen.findByText("Nenhum caso aberto para este cliente ainda."),
    ).toBeInTheDocument();
  });

  it("mostra acesso negado quando o cliente não existe para o tenant", async () => {
    getClientMock.mockRejectedValue(new ApiError(404, "Cliente não encontrado."));

    renderPage();

    expect(
      await screen.findByText("Este cliente não existe ou você não tem acesso a ele."),
    ).toBeInTheDocument();
  });

  it("mostra erro da API com opção de tentar novamente", async () => {
    getClientMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    renderPage();

    expect(await screen.findByText("Erro inesperado (HTTP 500).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });
});
