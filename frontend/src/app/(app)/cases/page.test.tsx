import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case, User } from "@/types/api";

import CasesPage from "./page";

const { listCasesMock } = vi.hoisted(() => ({ listCasesMock: vi.fn() }));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, listCases: listCasesMock } };
});

const useAuthMock = vi.fn();
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => useAuthMock() }));

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: null,
    area: null,
    matter: null,
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    status: "in_progress",
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
  listCasesMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
});

describe("CasesPage", () => {
  it("lista os casos do tenant autenticado", async () => {
    listCasesMock.mockResolvedValue([
      makeCase({ platform: "whatsapp", fraud_type: "pix" }),
      makeCase({ id: "22222222-2222-2222-2222-222222222222", platform: "shopee", fraud_type: "marketplace" }),
    ]);

    render(<CasesPage />);

    expect(screen.getByText("Carregando casos...")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("whatsapp")).toBeInTheDocument());
    expect(screen.getByText("shopee")).toBeInTheDocument();
    expect(listCasesMock).toHaveBeenCalledTimes(1);
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

    await waitFor(() => expect(screen.getByText("whatsapp")).toBeInTheDocument());
    expect(listCasesMock).toHaveBeenCalledTimes(2);
  });

  it("filtra a lista já carregada por busca e por status, sem nova chamada à API", async () => {
    listCasesMock.mockResolvedValue([
      makeCase({ platform: "whatsapp", status: "in_progress" }),
      makeCase({
        id: "22222222-2222-2222-2222-222222222222",
        platform: "shopee",
        status: "pending_approval",
      }),
    ]);

    render(<CasesPage />);
    await waitFor(() => expect(screen.getByText("whatsapp")).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText("Buscar casos"), "shopee");
    expect(screen.queryByText("whatsapp")).not.toBeInTheDocument();
    expect(screen.getByText("shopee")).toBeInTheDocument();
    expect(listCasesMock).toHaveBeenCalledTimes(1);
  });
});
