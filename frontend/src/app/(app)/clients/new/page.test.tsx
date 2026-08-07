import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import { makeClient } from "@/test/factories";
import type { User } from "@/types/api";

import NewClientPage from "./page";

const { createClientMock, pushMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, createClient: createClientMock } };
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
  createClientMock.mockReset();
  pushMock.mockReset();
  useAuthMock.mockReset();
  useAuthMock.mockReturnValue({ user: makeUser() });
});

describe("NewClientPage", () => {
  it("exige o nome do cliente e não chama a API sem ele", async () => {
    render(<NewClientPage />);

    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    expect(await screen.findByText("Informe o nome do cliente.")).toBeInTheDocument();
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it("cadastra com a qualificação completa e redireciona para a ficha", async () => {
    createClientMock.mockResolvedValue(makeClient());

    render(<NewClientPage />);

    await userEvent.type(screen.getByLabelText("Nome completo"), "Maria Souza de Oliveira");
    await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-25");
    await userEvent.type(screen.getByLabelText("Profissão"), "professora");
    await userEvent.selectOptions(screen.getByLabelText("Estado civil"), "married");
    await userEvent.type(screen.getByLabelText("Município"), "São Paulo");
    await userEvent.selectOptions(screen.getByLabelText("UF"), "SP");
    await userEvent.type(screen.getByLabelText("CEP"), "01310-100");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    await waitFor(() => expect(createClientMock).toHaveBeenCalled());
    const payload = createClientMock.mock.calls[0][0];
    expect(payload).toMatchObject({
      full_name: "Maria Souza de Oliveira",
      person_type: "individual",
      // Documento e CEP vão só com dígitos, como o backend armazena.
      document_number: "52998224725",
      address_zip_code: "01310100",
      address_state: "SP",
      profession: "professora",
      marital_status: "married",
    });
    expect(pushMock).toHaveBeenCalledWith("/clients/client-1");
  });

  it("omite campos em branco em vez de enviar string vazia", async () => {
    createClientMock.mockResolvedValue(makeClient());

    render(<NewClientPage />);

    await userEvent.type(screen.getByLabelText("Nome completo"), "Só o Nome");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    await waitFor(() => expect(createClientMock).toHaveBeenCalled());
    const payload = createClientMock.mock.calls[0][0];
    expect(payload).not.toHaveProperty("document_number");
    expect(payload).not.toHaveProperty("marital_status");
    expect(payload).not.toHaveProperty("address_city");
  });

  it("recusa CPF com dígito verificador errado antes de chamar a API", async () => {
    render(<NewClientPage />);

    await userEvent.type(screen.getByLabelText("Nome completo"), "CPF Inválido");
    await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-24");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    expect(await screen.findByText("CPF inválido — confira os dígitos.")).toBeInTheDocument();
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it("valida CNPJ quando a natureza é pessoa jurídica", async () => {
    createClientMock.mockResolvedValue(makeClient({ person_type: "company" }));

    render(<NewClientPage />);

    await userEvent.selectOptions(screen.getByLabelText("Natureza"), "company");
    await userEvent.type(screen.getByLabelText("Razão social"), "Comércio Exemplo LTDA");
    await userEvent.type(screen.getByLabelText(/^CNPJ/), "11.222.333/0001-81");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    await waitFor(() => expect(createClientMock).toHaveBeenCalled());
    expect(createClientMock.mock.calls[0][0]).toMatchObject({
      person_type: "company",
      document_number: "11222333000181",
    });
  });

  it("recusa CEP fora do formato", async () => {
    render(<NewClientPage />);

    await userEvent.type(screen.getByLabelText("Nome completo"), "CEP Errado");
    await userEvent.type(screen.getByLabelText("CEP"), "1310-10");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    expect(
      await screen.findByText("CEP inválido — informe 8 dígitos (ex.: 01310-100)."),
    ).toBeInTheDocument();
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it("mostra a mensagem de conflito do backend e não redireciona", async () => {
    createClientMock.mockRejectedValue(
      new ApiError(409, "Já existe um cliente com este CPF/CNPJ neste escritório."),
    );

    render(<NewClientPage />);

    await userEvent.type(screen.getByLabelText("Nome completo"), "Duplicado");
    await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-25");
    await userEvent.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Já existe um cliente com este CPF/CNPJ neste escritório.",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("nega o cadastro ao papel viewer", () => {
    useAuthMock.mockReturnValue({ user: makeUser({ role: "viewer" }) });

    render(<NewClientPage />);

    expect(
      screen.getByText("Seu papel neste escritório permite apenas consultar clientes."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Nome completo")).not.toBeInTheDocument();
  });
});
