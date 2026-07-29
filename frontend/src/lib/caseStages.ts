import type { ModuleName } from "@/types/api";

/**
 * As 6 etapas do workflow jurídico, na ordem fixa do backend
 * (orchestrator/router.py::MODULE_ORDER) — nunca reordenar sem checar o
 * backend primeiro.
 */
export interface CaseStage {
  module: ModuleName;
  /** Segmento de rota dentro de /cases/[caseId]/... (ver app/(app)/cases/[caseId]/*). */
  segment: string;
  label: string;
}

export const CASE_STAGES: readonly CaseStage[] = [
  { module: "intake", segment: "intake", label: "Intake" },
  { module: "evidence", segment: "evidencias", label: "Evidências" },
  { module: "research", segment: "pesquisa", label: "Pesquisa" },
  { module: "strategy", segment: "estrategia", label: "Estratégia" },
  { module: "drafting", segment: "minuta", label: "Minuta" },
  { module: "review", segment: "revisao", label: "Revisão" },
];

function stageIndex(module: ModuleName): number {
  return CASE_STAGES.findIndex((stage) => stage.module === module);
}

/**
 * Uma etapa está liberada se já foi alcançada ou é a etapa atual do caso
 * (`Case.current_module`, backend/app/models/case.py) — etapas futuras ficam
 * bloqueadas até o caso avançar (CLAUDE.md, seção 16: nunca simular avanço
 * de etapa só na interface).
 */
export function isStageUnlocked(currentModule: ModuleName, stage: CaseStage): boolean {
  return stageIndex(stage.module) <= stageIndex(currentModule);
}
