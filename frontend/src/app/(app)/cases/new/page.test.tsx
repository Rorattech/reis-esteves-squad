import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case } from "@/types/api";

import NewCasePage from "./page";

const { createCaseMock, pushMock } = vi.hoisted(() => ({
  createCaseMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, createCase: createCaseMock } };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    tenant_id: "tenant-1",
    user_id: "user-1",
    client_id: null,
    area: null,
    matter: null,
    platform: "whatsapp",
    fraud_type: "pix",
    urgency: "high",
    status: "draft",
    current_module: "intake",
    human_review_required: true,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  createCaseMock.mockReset();
  pushMock.mockReset();
});

describe("NewCasePage", () => {
  it("mostra erros de validação e não chama a API quando os campos obrigatórios estão vazios", async () => {
    render(<NewCasePage />);

    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    expect(await screen.findByText("Informe a plataforma envolvida.")).toBeInTheDocument();
    expect(screen.getByText("Selecione a modalidade do golpe.")).toBeInTheDocument();
    expect(createCaseMock).not.toHaveBeenCalled();
  });

  it("cria o caso e redireciona para o detalhe após sucesso", async () => {
    createCaseMock.mockResolvedValue(makeCase());

    render(<NewCasePage />);

    await userEvent.type(screen.getByLabelText("Plataforma envolvida"), "WhatsApp");
    await userEvent.selectOptions(screen.getByLabelText("Modalidade do golpe"), "pix");
    await userEvent.selectOptions(screen.getByLabelText("Urgência"), "high");
    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    await waitFor(() =>
      expect(createCaseMock).toHaveBeenCalledWith({
        platform: "WhatsApp",
        fraud_type: "pix",
        urgency: "high",
      }),
    );
    expect(pushMock).toHaveBeenCalledWith("/cases/33333333-3333-3333-3333-333333333333");
  });

  it("mostra a mensagem de erro da API e não redireciona quando a criação falha", async () => {
    createCaseMock.mockRejectedValue(new ApiError(403, "Usuário não tem papel autorizado."));

    render(<NewCasePage />);

    await userEvent.type(screen.getByLabelText("Plataforma envolvida"), "WhatsApp");
    await userEvent.selectOptions(screen.getByLabelText("Modalidade do golpe"), "pix");
    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    expect(await screen.findByText("Usuário não tem papel autorizado.")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
