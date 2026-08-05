import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case } from "@/types/api";

import CaseLayout from "./layout";

const { getCaseMock } = vi.hoisted(() => ({ getCaseMock: vi.fn() }));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, getCase: getCaseMock } };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "44444444-4444-4444-4444-444444444444" }),
  usePathname: () => "/cases/44444444-4444-4444-4444-444444444444",
}));

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "44444444-4444-4444-4444-444444444444",
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: null,
    area: null,
    matter: null,
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    status: "in_progress",
    current_module: "evidence",
    human_review_required: false,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  getCaseMock.mockReset();
});

describe("CaseLayout", () => {
  it("mostra o caso, o status e a etapa atual liberada quando o backend responde normalmente", async () => {
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    await waitFor(() => expect(screen.getByText("whatsapp")).toBeInTheDocument());
    expect(screen.getByText("Em andamento")).toBeInTheDocument();
    expect(screen.getByText("conteúdo da aba")).toBeInTheDocument();
    // current_module = "evidence": Abertura de caso e Evidências liberadas, o
    // restante bloqueado.
    expect(screen.getByRole("link", { name: "Abertura de caso" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidências" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Pesquisa" })).not.toBeInTheDocument();
    expect(screen.getByText("Pesquisa")).toHaveAttribute("aria-disabled", "true");
  });

  it("mostra acesso negado (sem vazar detalhes) quando o caso não existe para o tenant", async () => {
    getCaseMock.mockRejectedValue(new ApiError(404, "Caso não encontrado."));

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    expect(
      await screen.findByText("Este caso não existe ou você não tem acesso a ele."),
    ).toBeInTheDocument();
    expect(screen.queryByText("conteúdo da aba")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar para Casos" })).toBeInTheDocument();
  });

  it("mostra erro genérico com opção de tentar novamente para falhas que não são 404", async () => {
    getCaseMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    expect(await screen.findByText("Erro inesperado (HTTP 500).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });
});
