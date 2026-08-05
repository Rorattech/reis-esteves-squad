import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseStageGuide } from "@/components/cases/CaseStageGuide";
import type { Case } from "@/types/api";

const BASE_PATH = "/cases/77777777-7777-7777-7777-777777777777";

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "77777777-7777-7777-7777-777777777777",
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
    human_review_required: false,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}

describe("CaseStageGuide", () => {
  it("mostra a posição no workflow, a ação de avanço e o link para a etapa", () => {
    render(<CaseStageGuide caseData={makeCase()} basePath={BASE_PATH} />);

    expect(screen.getByText("Etapa 1 de 6 · Abertura de caso")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Complete a abertura do caso/ })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Abrir a etapa Abertura de caso/ }),
    ).toHaveAttribute("href", `${BASE_PATH}/intake`);
  });

  it("aponta a revisão da triagem quando existe recomendação pendente", () => {
    render(
      <CaseStageGuide caseData={makeCase({ status: "pending_approval" })} basePath={BASE_PATH} />,
    );

    expect(
      screen.getByRole("heading", { name: /Revise a recomendação da triagem/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Revisar a triagem/ })).toBeInTheDocument();
  });

  it("acompanha a etapa atual do caso definida pelo backend", () => {
    render(
      <CaseStageGuide
        caseData={makeCase({ current_module: "evidence", status: "in_progress" })}
        basePath={BASE_PATH}
      />,
    );

    expect(screen.getByText("Etapa 2 de 6 · Evidências")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Abrir a etapa Evidências/ })).toHaveAttribute(
      "href",
      `${BASE_PATH}/evidencias`,
    );
  });

  it("não repete o botão quando o advogado já está na aba da etapa atual", () => {
    render(<CaseStageGuide caseData={makeCase()} basePath={BASE_PATH} showCta={false} />);

    expect(screen.getByText("Etapa 1 de 6 · Abertura de caso")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("diz que a etapa não existe no produto em vez de prometer conteúdo", () => {
    render(
      <CaseStageGuide
        caseData={makeCase({ current_module: "drafting", status: "in_progress" })}
        basePath={BASE_PATH}
      />,
    );

    expect(screen.getByRole("heading", { name: /ainda não está disponível no produto/ })).toBeInTheDocument();
  });
});
