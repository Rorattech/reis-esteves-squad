import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import type { Case } from "@/types/api";

import CaseLayout from "./layout";
import { makeCase as makeBaseCase } from "@/test/factories";

/** Caso base destes testes — o caso destes testes já está na etapa de Evidências. */
function makeCase(overrides: Partial<Case> = {}): Case {
  return makeBaseCase({ current_module: "evidence", ...overrides });
}

const { getCaseMock } = vi.hoisted(() => ({ getCaseMock: vi.fn() }));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, api: { ...actual.api, getCase: getCaseMock } };
});

const CASE_ID = "44444444-4444-4444-4444-444444444444";
const BASE_PATH = `/cases/${CASE_ID}`;

/** Aba aberta no momento — cada teste ajusta para simular a URL visitada. */
let pathname = BASE_PATH;

vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "44444444-4444-4444-4444-444444444444" }),
  usePathname: () => pathname,
}));


beforeEach(() => {
  getCaseMock.mockReset();
  pathname = BASE_PATH;
});

describe("CaseLayout", () => {
  it("mostra o caso, o status e a etapa atual liberada quando o backend responde normalmente", async () => {
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    // O cabeçalho identifica o caso pelo código legível e pelo nome do
    // cliente — o UUID fica só na URL.
    await waitFor(() => expect(screen.getByText(/CAS-2026-000001/)).toBeInTheDocument());
    expect(screen.getByText("Em andamento")).toBeInTheDocument();
    expect(screen.getByText("conteúdo da aba")).toBeInTheDocument();
    // current_module = "evidence": Abertura de caso e Evidências liberadas, o
    // restante bloqueado.
    expect(screen.getByRole("link", { name: "Abertura de caso" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidências" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Pesquisa" })).not.toBeInTheDocument();
    expect(screen.getByText("Pesquisa")).toHaveAttribute("aria-disabled", "true");
  });

  it("nomeia a situação de cada etapa em texto, não só em cor", async () => {
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    // current_module = "evidence": 1 concluída, 1 atual, 4 bloqueadas.
    await waitFor(() => expect(screen.getAllByText("Concluída")).toHaveLength(1));
    expect(screen.getAllByText("Etapa atual")).toHaveLength(1);
    expect(screen.getAllByText("Bloqueada")).toHaveLength(4);
  });

  it("orienta a próxima ação com link para a etapa atual quando o advogado está em outra aba", async () => {
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    await waitFor(() =>
      expect(screen.getByText("Etapa 2 de 6 · Evidências")).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /Abrir a etapa Evidências/ })).toHaveAttribute(
      "href",
      `${BASE_PATH}/evidencias`,
    );
  });

  it("não repete o botão de próxima ação quando a aba aberta já é a da etapa atual", async () => {
    pathname = `${BASE_PATH}/evidencias`;
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    await waitFor(() => expect(screen.getByText("conteúdo da aba")).toBeInTheDocument());
    expect(screen.getByText("Etapa 2 de 6 · Evidências")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Abrir a etapa Evidências/ })).not.toBeInTheDocument();
  });

  it("explica a etapa bloqueada aberta por URL direta em vez de mostrar a aba vazia", async () => {
    pathname = `${BASE_PATH}/minuta`;
    getCaseMock.mockResolvedValue(makeCase());

    render(
      <CaseLayout>
        <p>conteúdo da aba</p>
      </CaseLayout>,
    );

    expect(await screen.findByText("Minuta ainda não foi liberada")).toBeInTheDocument();
    // O conteúdo da etapa bloqueada não é renderizado.
    expect(screen.queryByText("conteúdo da aba")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para Evidências" })).toHaveAttribute(
      "href",
      `${BASE_PATH}/evidencias`,
    );
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
