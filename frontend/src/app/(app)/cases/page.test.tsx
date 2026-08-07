import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, User } from "@/types/api";

import CasesPage from "./page";
import { makeCase, makeClientSummary } from "@/test/factories";

const { listCasesMock, deleteCaseMock, pushMock } = vi.hoisted(() => ({
  listCasesMock: vi.fn(),
  deleteCaseMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: { ...actual.api, listCases: listCasesMock, deleteCase: deleteCaseMock },
  };
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
  listCasesMock.mockReset();
  deleteCaseMock.mockReset();
  pushMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
});

describe("CasesPage", () => {
  it("lista os casos do tenant autenticado", async () => {
    listCasesMock.mockResolvedValue([
      makeCase({ client: makeClientSummary() }),
      makeCase({
        id: "22222222-2222-2222-2222-222222222222",
        code: "CAS-2026-000002",
        platform: "Shopee",
      }),
    ]);

    render(<CasesPage />);

    expect(screen.getByText("Carregando casos...")).toBeInTheDocument();

    // O advogado enxerga código e nome — nenhum UUID aparece na tela.
    await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());
    expect(screen.getByText("CAS-2026-000002")).toBeInTheDocument();
    expect(screen.getByText("Maria Souza de Oliveira")).toBeInTheDocument();
    expect(
      screen.queryByText("11111111-1111-1111-1111-111111111111"),
    ).not.toBeInTheDocument();
  });

  it("mostra o estado vazio com ação de criar caso quando não há casos", async () => {
    listCasesMock.mockResolvedValue([]);

    render(<CasesPage />);

    await waitFor(() => expect(screen.getByText("Nenhum caso ainda")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Criar caso" })).toHaveAttribute("href", "/cases/new");
  });

  it("não mostra a ação de criar caso para o papel viewer", async () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });
    listCasesMock.mockResolvedValue([]);

    render(<CasesPage />);

    await waitFor(() => expect(screen.getByText("Nenhum caso ainda")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "Criar caso" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Novo caso" })).not.toBeInTheDocument();
  });

  it("mostra erro com opção de tentar novamente quando a API falha", async () => {
    listCasesMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    render(<CasesPage />);

    await waitFor(() =>
      expect(screen.getByText("Erro inesperado (HTTP 500).")).toBeInTheDocument(),
    );

    listCasesMock.mockResolvedValueOnce([makeCase()]);
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

    await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());
    expect(listCasesMock).toHaveBeenCalledTimes(2);
  });

  it("delega busca e filtro ao backend, que é quem enxerga o nome do cliente", async () => {
    listCasesMock.mockResolvedValue([makeCase({ client: makeClientSummary() })]);

    render(<CasesPage />);
    await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

    listCasesMock.mockResolvedValue([]);
    // fireEvent.change em vez de userEvent.type: o que importa aqui é o termo
    // final chegar ao backend, não a digitação tecla a tecla (que a busca
    // debounced descarta de propósito).
    fireEvent.change(screen.getByLabelText("Buscar casos"), { target: { value: "Maria" } });

    // Busca no servidor: filtrar aqui exigiria baixar a base inteira com os nomes.
    // waitFor porque a busca é debounced — as teclas intermediárias não
    // disparam request própria.
    await waitFor(() =>
      expect(listCasesMock.mock.lastCall?.[0]).toMatchObject({ search: "Maria" }),
    );
    expect(screen.getByText("Nenhum caso encontrado")).toBeInTheDocument();
  });

  it("mantém o campo de busca quando o filtro não encontra nada", async () => {
    // Sem essa distinção, "nada encontrado" cairia no estado de escritório
    // vazio e esconderia a busca, deixando o advogado sem saída.
    listCasesMock.mockResolvedValue([makeCase()]);
    render(<CasesPage />);
    await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

    listCasesMock.mockResolvedValue([]);
    fireEvent.change(screen.getByLabelText("Buscar casos"), {
      target: { value: "inexistente" },
    });

    await waitFor(() => expect(screen.getByText("Nenhum caso encontrado")).toBeInTheDocument());
    expect(screen.getByLabelText("Buscar casos")).toBeInTheDocument();
    expect(screen.queryByText("Nenhum caso ainda")).not.toBeInTheDocument();
  });

  it("mostra a etapa de abertura com o nome usado pelo advogado", async () => {
    listCasesMock.mockResolvedValue([makeCase({ current_module: "intake" })]);

    render(<CasesPage />);

    await waitFor(() => expect(screen.getByText("Abertura de caso")).toBeInTheDocument());
    expect(screen.queryByText("Intake")).not.toBeInTheDocument();
  });

  describe("navegação e ações da linha", () => {
    it("navega para o caso ao clicar em qualquer parte da linha", async () => {
      listCasesMock.mockResolvedValue([makeCase()]);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      // Célula que não é link nem botão — só a linha inteira pode responder.
      await userEvent.click(screen.getByText("Golpe do PIX"));

      expect(pushMock).toHaveBeenCalledWith("/cases/11111111-1111-1111-1111-111111111111");
    });

    it("abre a edição sem disparar a navegação da linha", async () => {
      listCasesMock.mockResolvedValue([makeCase()]);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      const editLink = screen.getByRole("link", { name: "Editar caso CAS-2026-000001" });
      expect(editLink).toHaveAttribute(
        "href",
        "/cases/11111111-1111-1111-1111-111111111111/editar",
      );

      await userEvent.click(editLink);
      expect(pushMock).not.toHaveBeenCalled();
    });

    it("exclui o caso após confirmação, sem navegar para ele", async () => {
      listCasesMock.mockResolvedValue([makeCase()]);
      deleteCaseMock.mockResolvedValue(undefined);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      await userEvent.click(screen.getByRole("button", { name: "Excluir caso CAS-2026-000001" }));
      expect(pushMock).not.toHaveBeenCalled();

      // Ação irreversível: só executa depois da confirmação explícita.
      expect(deleteCaseMock).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Excluir caso" }));

      await waitFor(() =>
        expect(deleteCaseMock).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111"),
      );
      // Recarrega a lista a partir do backend em vez de removê-la da tela.
      await waitFor(() => expect(listCasesMock).toHaveBeenCalledTimes(2));
      expect(pushMock).not.toHaveBeenCalled();
    });

    it("cancela a exclusão sem chamar a API", async () => {
      listCasesMock.mockResolvedValue([makeCase()]);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      await userEvent.click(screen.getByRole("button", { name: "Excluir caso CAS-2026-000001" }));
      await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

      expect(deleteCaseMock).not.toHaveBeenCalled();
      expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument();
    });

    it("mostra erro da API quando a exclusão falha e mantém o caso na lista", async () => {
      listCasesMock.mockResolvedValue([makeCase()]);
      deleteCaseMock.mockRejectedValue(new ApiError(403, "Usuário não tem papel autorizado."));

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      await userEvent.click(screen.getByRole("button", { name: "Excluir caso CAS-2026-000001" }));
      await userEvent.click(screen.getByRole("button", { name: "Excluir caso" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Usuário não tem papel autorizado.",
      );
      expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument();
    });

    it("não oferece exclusão para paralegal, que pode editar mas não excluir", async () => {
      useAuthMock.mockReturnValue({ user: makeUser({ role: "paralegal" }) });
      listCasesMock.mockResolvedValue([makeCase()]);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      expect(screen.getByRole("link", { name: "Editar caso CAS-2026-000001" })).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Excluir caso CAS-2026-000001" }),
      ).not.toBeInTheDocument();
    });

    it("não oferece nenhuma ação de escrita para viewer", async () => {
      useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });
      listCasesMock.mockResolvedValue([makeCase()]);

      render(<CasesPage />);
      await waitFor(() => expect(screen.getByText("CAS-2026-000001")).toBeInTheDocument());

      expect(screen.queryByRole("link", { name: "Editar caso CAS-2026-000001" })).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Excluir caso CAS-2026-000001" }),
      ).not.toBeInTheDocument();
    });
  });
});
