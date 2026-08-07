import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import {
  makeCase as makeBaseCase,
  makeClient,
  makeFraudModality,
  makePlatform,
} from "@/test/factories";
import type { Case } from "@/types/api";

import NewCasePage from "./page";

/** Caso base destes testes — caso recém-aberto, ainda em rascunho. */
function makeCase(overrides: Partial<Case> = {}): Case {
  return makeBaseCase({ status: "draft", ...overrides });
}

const SHOPEE = makePlatform({ id: "platform-2", slug: "shopee", label: "Shopee", sort_order: 60 });
const MARKETPLACE = makeFraudModality({
  id: "modality-2",
  slug: "marketplace",
  label: "Compra não entregue em marketplace",
  family: "marketplace",
  sort_order: 40,
});

const {
  createCaseMock,
  listPlatformsMock,
  listFraudModalitiesMock,
  listClientsMock,
  createPlatformMock,
  createFraudModalityMock,
  pushMock,
} = vi.hoisted(() => ({
  createCaseMock: vi.fn(),
  listPlatformsMock: vi.fn(),
  listFraudModalitiesMock: vi.fn(),
  listClientsMock: vi.fn(),
  createPlatformMock: vi.fn(),
  createFraudModalityMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      createCase: createCaseMock,
      listPlatforms: listPlatformsMock,
      listFraudModalities: listFraudModalitiesMock,
      listClients: listClientsMock,
      createPlatform: createPlatformMock,
      createFraudModality: createFraudModalityMock,
    },
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  createCaseMock.mockReset();
  listPlatformsMock.mockReset();
  listFraudModalitiesMock.mockReset();
  listClientsMock.mockReset();
  createPlatformMock.mockReset();
  createFraudModalityMock.mockReset();
  pushMock.mockReset();

  listPlatformsMock.mockResolvedValue([makePlatform(), SHOPEE]);
  listFraudModalitiesMock.mockResolvedValue([makeFraudModality(), MARKETPLACE]);
  listClientsMock.mockResolvedValue([]);
});

/** Espera o catálogo carregar — o formulário só aparece depois dele. */
async function renderForm() {
  render(<NewCasePage />);
  expect(screen.getByText("Carregando catálogo de classificação...")).toBeInTheDocument();
  await screen.findByLabelText("Plataforma envolvida");
}

async function selectClassification() {
  await userEvent.selectOptions(screen.getByLabelText("Plataforma envolvida"), SHOPEE.id);
  await userEvent.selectOptions(screen.getByLabelText("Modalidade do golpe"), MARKETPLACE.id);
}

describe("NewCasePage", () => {
  it("mostra erros de validação e não chama a API quando a classificação está vazia", async () => {
    await renderForm();

    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    expect(await screen.findByText("Selecione a plataforma envolvida.")).toBeInTheDocument();
    expect(screen.getByText("Selecione a modalidade do golpe.")).toBeInTheDocument();
    expect(createCaseMock).not.toHaveBeenCalled();
  });

  it("classifica o caso por entradas do catálogo, não por texto livre", async () => {
    createCaseMock.mockResolvedValue(makeCase());
    await renderForm();

    // Plataforma virou <select>: não existe mais campo de texto para digitar
    // "whatsapp" e "WhatsApp" como se fossem plataformas diferentes.
    expect(screen.getByLabelText("Plataforma envolvida").tagName).toBe("SELECT");

    await selectClassification();
    await userEvent.selectOptions(screen.getByLabelText("Urgência"), "high");
    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    await waitFor(() =>
      expect(createCaseMock).toHaveBeenCalledWith({
        platform_id: SHOPEE.id,
        fraud_modality_id: MARKETPLACE.id,
        urgency: "high",
      }),
    );
    expect(pushMock).toHaveBeenCalledWith("/cases/11111111-1111-1111-1111-111111111111");
  });

  it("mostra a mensagem de erro da API e não redireciona quando a criação falha", async () => {
    createCaseMock.mockRejectedValue(new ApiError(403, "Usuário não tem papel autorizado."));
    await renderForm();

    await selectClassification();
    await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

    expect(await screen.findByText("Usuário não tem papel autorizado.")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("mostra o erro da API quando o catálogo não carrega, com opção de tentar novamente", async () => {
    listPlatformsMock.mockRejectedValue(new ApiError(500, "Erro inesperado (HTTP 500)."));

    render(<NewCasePage />);

    expect(await screen.findByText("Erro inesperado (HTTP 500).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  describe("cliente", () => {
    it("busca o cliente por nome em vez de pedir um UUID colado à mão", async () => {
      createCaseMock.mockResolvedValue(makeCase());
      listClientsMock.mockResolvedValue([makeClient()]);
      await renderForm();

      // O campo "Token do cliente" não existe mais.
      expect(screen.queryByLabelText(/Token do cliente/)).not.toBeInTheDocument();

      await userEvent.click(await screen.findByText("Maria Souza de Oliveira"));
      await selectClassification();
      await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

      await waitFor(() =>
        expect(createCaseMock).toHaveBeenCalledWith(
          expect.objectContaining({ client_id: "client-1" }),
        ),
      );
    });

    it("envia o cliente novo aninhado, para caso e cadastro nascerem na mesma transação", async () => {
      createCaseMock.mockResolvedValue(makeCase());
      await renderForm();

      await userEvent.click(screen.getByRole("button", { name: "Cadastrar novo cliente" }));
      await userEvent.type(screen.getByLabelText("Nome completo"), "Marta Ribeiro");
      await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-25");
      await userEvent.type(screen.getByLabelText("Município"), "Santos");
      await userEvent.selectOptions(screen.getByLabelText("UF"), "SP");
      await userEvent.click(screen.getByRole("button", { name: "Usar este cliente" }));

      await selectClassification();
      await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

      await waitFor(() => expect(createCaseMock).toHaveBeenCalled());
      const payload = createCaseMock.mock.calls[0][0];
      expect(payload.client).toMatchObject({
        full_name: "Marta Ribeiro",
        // Documento vai só com dígitos, como o backend armazena.
        document_number: "52998224725",
        address_city: "Santos",
        address_state: "SP",
      });
      expect(payload).not.toHaveProperty("client_id");
    });

    it("recusa CPF com dígito verificador errado sem chamar a API", async () => {
      await renderForm();

      await userEvent.click(screen.getByRole("button", { name: "Cadastrar novo cliente" }));
      await userEvent.type(screen.getByLabelText("Nome completo"), "CPF Inválido");
      await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-24");
      await userEvent.click(screen.getByRole("button", { name: "Usar este cliente" }));

      expect(await screen.findByText("CPF inválido — confira os dígitos.")).toBeInTheDocument();
      expect(createCaseMock).not.toHaveBeenCalled();
    });

    it("omite os campos opcionais em branco em vez de mandar string vazia", async () => {
      createCaseMock.mockResolvedValue(makeCase());
      await renderForm();

      await selectClassification();
      await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

      await waitFor(() => expect(createCaseMock).toHaveBeenCalled());
      const payload = createCaseMock.mock.calls[0][0];
      expect(payload).not.toHaveProperty("client_id");
      expect(payload).not.toHaveProperty("client");
      expect(payload).not.toHaveProperty("area");
      expect(payload).not.toHaveProperty("matter");
    });
  });

  describe("catálogo", () => {
    it("cadastra uma modalidade nova pela opção Outro, com família obrigatória", async () => {
      const created = makeFraudModality({
        id: "modality-3",
        slug: "golpe_da_falsa_central",
        label: "Golpe da falsa central",
        family: "pix",
      });
      createFraudModalityMock.mockResolvedValue(created);
      createCaseMock.mockResolvedValue(makeCase());
      await renderForm();

      await userEvent.selectOptions(screen.getByLabelText("Modalidade do golpe"), "__create__");
      await userEvent.type(screen.getByLabelText("Descreva o golpe"), "Golpe da falsa central");
      await userEvent.selectOptions(screen.getByLabelText("Família"), "pix");
      await userEvent.click(screen.getByRole("button", { name: "Salvar modalidade" }));

      await waitFor(() =>
        expect(createFraudModalityMock).toHaveBeenCalledWith({
          label: "Golpe da falsa central",
          family: "pix",
        }),
      );

      await userEvent.selectOptions(screen.getByLabelText("Plataforma envolvida"), SHOPEE.id);
      await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

      await waitFor(() =>
        expect(createCaseMock).toHaveBeenCalledWith(
          expect.objectContaining({ fraud_modality_id: created.id }),
        ),
      );
    });

    it("preserva o cliente já escolhido ao cadastrar uma plataforma nova", async () => {
      // Recarregar o catálogo não pode desmontar o formulário: fazia o
      // advogado perder o cliente que acabara de buscar.
      const kwai = makePlatform({ id: "platform-9", slug: "kwai", label: "Kwai" });
      createPlatformMock.mockResolvedValue(kwai);
      listClientsMock.mockResolvedValue([makeClient()]);
      createCaseMock.mockResolvedValue(makeCase());
      await renderForm();

      await userEvent.click(await screen.findByText("Maria Souza de Oliveira"));
      expect(screen.getByText(/CLI-000001/)).toBeInTheDocument();

      listPlatformsMock.mockResolvedValue([makePlatform(), SHOPEE, kwai]);
      await userEvent.selectOptions(screen.getByLabelText("Plataforma envolvida"), "__create__");
      await userEvent.type(screen.getByLabelText("Nome da plataforma"), "Kwai");
      await userEvent.click(screen.getByRole("button", { name: "Salvar plataforma" }));

      await waitFor(() => expect(createPlatformMock).toHaveBeenCalled());
      // O cliente continua selecionado, e o formulário não voltou ao estado de
      // carregamento.
      expect(screen.getByText(/CLI-000001/)).toBeInTheDocument();
      expect(
        screen.queryByText("Carregando catálogo de classificação..."),
      ).not.toBeInTheDocument();

      await userEvent.selectOptions(screen.getByLabelText("Modalidade do golpe"), MARKETPLACE.id);
      await userEvent.click(screen.getByRole("button", { name: "Criar caso" }));

      await waitFor(() =>
        expect(createCaseMock).toHaveBeenCalledWith(
          expect.objectContaining({ platform_id: kwai.id, client_id: "client-1" }),
        ),
      );
    });

    it("mostra o conflito do backend quando a entrada já existe no catálogo", async () => {
      createPlatformMock.mockRejectedValue(
        new ApiError(409, "Já existe uma entrada com este nome no catálogo do escritório."),
      );
      await renderForm();

      await userEvent.selectOptions(screen.getByLabelText("Plataforma envolvida"), "__create__");
      await userEvent.type(screen.getByLabelText("Nome da plataforma"), "Shopee");
      await userEvent.click(screen.getByRole("button", { name: "Salvar plataforma" }));

      expect(
        await screen.findByText("Já existe uma entrada com este nome no catálogo do escritório."),
      ).toBeInTheDocument();
    });
  });
});
