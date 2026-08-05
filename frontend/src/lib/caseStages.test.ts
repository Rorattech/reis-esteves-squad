import { describe, expect, it } from "vitest";

import {
  CASE_STAGES,
  isStageUnlocked,
  stageForSegment,
  stageGuidance,
  stageNumber,
  stageProgress,
} from "@/lib/caseStages";
import type { Case } from "@/types/api";

const INTAKE = CASE_STAGES[0];
const EVIDENCE = CASE_STAGES[1];
const RESEARCH = CASE_STAGES[2];

function caseAt(current_module: Case["current_module"], status: Case["status"]) {
  return { current_module, status };
}

describe("stageProgress", () => {
  it("classifica etapas anteriores, atual e futuras a partir da etapa do caso", () => {
    expect(stageProgress("evidence", INTAKE)).toBe("done");
    expect(stageProgress("evidence", EVIDENCE)).toBe("current");
    expect(stageProgress("evidence", RESEARCH)).toBe("locked");
  });

  it("mantém a coerência com isStageUnlocked (só etapa bloqueada não é navegável)", () => {
    for (const stage of CASE_STAGES) {
      expect(isStageUnlocked("evidence", stage)).toBe(stageProgress("evidence", stage) !== "locked");
    }
  });
});

describe("stageNumber e stageForSegment", () => {
  it("numera as etapas a partir de 1, na ordem do backend", () => {
    expect(stageNumber("intake")).toBe(1);
    expect(stageNumber("evidence")).toBe(2);
    expect(stageNumber("review")).toBe(CASE_STAGES.length);
  });

  it("resolve o segmento de rota de uma etapa e ignora abas que não são etapa", () => {
    expect(stageForSegment("evidencias")?.module).toBe("evidence");
    expect(stageForSegment("historico")).toBeNull();
    expect(stageForSegment("")).toBeNull();
  });
});

describe("stageGuidance", () => {
  it("na abertura sem recomendação, orienta completar a abertura para liberar Evidências", () => {
    const guidance = stageGuidance(caseAt("intake", "draft"));

    expect(guidance.position).toBe("Etapa 1 de 6 · Abertura de caso");
    expect(guidance.title).toContain("Complete a abertura do caso");
    expect(guidance.stage.segment).toBe("intake");
    expect(guidance.notImplementedYet).toBe(false);
  });

  it("com recomendação pendente, orienta revisar a triagem — o caminho real de avanço", () => {
    const guidance = stageGuidance(caseAt("intake", "pending_approval"));

    expect(guidance.title).toContain("Revise a recomendação da triagem");
    expect(guidance.ctaLabel).toBe("Revisar a triagem");
  });

  it("em evidências, aponta a etapa e a ação correspondentes", () => {
    const guidance = stageGuidance(caseAt("evidence", "in_progress"));

    expect(guidance.position).toBe("Etapa 2 de 6 · Evidências");
    expect(guidance.stage.segment).toBe("evidencias");
    expect(guidance.ctaLabel).toBe("Abrir a etapa Evidências");
  });

  it("assume que etapas sem interface ainda não estão disponíveis, sem prometer conteúdo", () => {
    const guidance = stageGuidance(caseAt("strategy", "in_progress"));

    expect(guidance.notImplementedYet).toBe(true);
    expect(guidance.title).toContain("ainda não está disponível");
  });

  it("não sugere avanço em caso arquivado", () => {
    expect(stageGuidance(caseAt("intake", "archived")).title).toBe("Caso arquivado");
  });
});
