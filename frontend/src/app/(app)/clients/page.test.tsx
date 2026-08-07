import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import { makeClient } from "@/test/factories";
import type { User } from "@/types/api";

import ClientsPage from "./page";

const { listClientsMock, pushMock } = vi.hoisted(() => ({
  listClientsMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, listClients: listClientsMock } };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

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
  listClientsMock.mockReset();
  pushMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
});

describe("ClientsPage", () => {
  it("mostra o estado de carregamento antes dos dados chegarem", () => {
    listClientsMock.mockReturnValue(new Promise(() => {}));

    render(<ClientsPage />);

    expect(screen.getByText("Carregando clientes...")).toBeInTheDocument();
  });

  it("lista os clientes com código, nome e documento formatado", async () => {
    listClientsMock.mockResolvedValue([makeClient()]);

    render(<ClientsPage />);

    await waitFor(() => expect(screen.getByText("CLI-000001")).toBeInTheDocument());
    expect(screen.getByText("Maria Souza de Oliveira")).toBeInTheDocument();
    // O backend guarda só dígitos; a máscara é da interface.
    expect(screen.getByText("529.982.247-25")).toBeInTheDocument();
    expect(screen.getByText("São Paulo/SP")).toBeInTheDocument();
    // Nenhum UUID visível na tela.
    expect(screen.queryByText("client-1")).not.toBeInTheDocument();
  });

  it("mostra o estado vazio com ação de cadastrar quando não há clientes", async () => {
    listClientsMock.mockResolvedValue([]);

    render(<ClientsPage />);

    await waitFor(() =>
      expect(screen.getByText("Nenhum cliente cadastrado")).toBeInTheDocument(),
    );
    // Aparece duas vezes de propósito: no cabeçalho e como ação do estado vazio.
    for (const link of screen.getAllByRole("link", { name: "Novo cliente" })) {
      expect(link).toHaveAttribute("href", "/clients/new");
    }
  });

  it("não oferece cadastro ao papel viewer", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });
    listClientsMock.mockResolvedValue([]);

    render(<ClientsPage />);

    await waitFor(() =>
      expect(screen.getByText("Nenhum cliente cadastrado")).toBeInTheDocument(),
    );
    expect(screen.queryAllByRole("link", { name: "Novo cliente" })).toHaveLength(0);
  });

  it("delega a busca ao backend e mantém o campo quando nada é encontrado", async () => {
    listClientsMock.mockResolvedValue([makeClient()]);

    render(<ClientsPage />);
    await waitFor(() => expect(screen.getByText("CLI-000001")).toBeInTheDocument());

    listClientsMock.mockResolvedValue([]);
    fireEvent.change(screen.getByLabelText("Buscar clientes"), {
      target: { value: "529.982.247-25" },
    });

    await waitFor(() =>
      expect(listClientsMock).toHaveBeenLastCalledWith("529.982.247-25"),
    );
    await waitFor(() =>
      expect(screen.getByText("Nenhum cliente encontrado")).toBeInTheDocument(),
    );
    // Sem essa distinção o campo de busca sumiria e o advogado ficaria sem saída.
    expect(screen.getByLabelText("Buscar clientes")).toBeInTheDocument();
    expect(screen.queryByText("Nenhum cliente cadastrado")).not.toBeInTheDocument();
  });

  it("mostra erro da API com opção de tentar novamente", async () => {
    listClientsMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    render(<ClientsPage />);

    await waitFor(() =>
      expect(screen.getByText("Erro inesperado (HTTP 500).")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("navega para a ficha ao clicar na linha", async () => {
    listClientsMock.mockResolvedValue([makeClient()]);

    render(<ClientsPage />);
    await waitFor(() => expect(screen.getByText("CLI-000001")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Maria Souza de Oliveira"));

    expect(pushMock).toHaveBeenCalledWith("/clients/client-1");
  });
});
