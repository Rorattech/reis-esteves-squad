import type { Case, CaseStatus, ModuleName } from "@/types/api";

/**
 * As 6 etapas do workflow jurídico, na ordem fixa do backend
 * (orchestrator/router.py::MODULE_ORDER) — nunca reordenar sem checar o
 * backend primeiro.
 */
export interface CaseStage {
  module: ModuleName;
  /** Segmento de rota dentro de /cases/[caseId]/... (ver app/(app)/cases/[caseId]/*). */
  segment: string;
  /**
   * Nome da etapa como o advogado a conhece. É rótulo de interface, e só —
   * o backend continua chamando o módulo de "intake" (ModuleName), então
   * nunca derive `module` ou `segment` a partir daqui.
   */
  label: string;
}

export const CASE_STAGES: readonly CaseStage[] = [
  { module: "intake", segment: "intake", label: "Abertura de caso" },
  { module: "evidence", segment: "evidencias", label: "Evidências" },
  { module: "research", segment: "pesquisa", label: "Pesquisa" },
  { module: "strategy", segment: "estrategia", label: "Estratégia" },
  { module: "drafting", segment: "minuta", label: "Minuta" },
  { module: "review", segment: "revisao", label: "Revisão" },
];

/**
 * Etapas que já têm interface e endpoints de verdade (Fases 2 e 3 do
 * roadmap). As outras existem como etapa do workflow no backend, mas abrir a
 * aba só mostra uma vitrine vazia — a orientação de etapa diz isso em vez de
 * sugerir que há trabalho a fazer lá.
 */
const IMPLEMENTED_MODULES: ReadonlySet<ModuleName> = new Set<ModuleName>(["intake", "evidence"]);

function stageIndex(module: ModuleName): number {
  return CASE_STAGES.findIndex((stage) => stage.module === module);
}

/** Etapa correspondente a um módulo do backend (cai na primeira se o módulo for desconhecido). */
export function stageFor(module: ModuleName): CaseStage {
  return CASE_STAGES.find((stage) => stage.module === module) ?? CASE_STAGES[0];
}

/** Etapa correspondente a um segmento de rota, ou null quando o segmento não é de etapa (ex.: "historico"). */
export function stageForSegment(segment: string): CaseStage | null {
  return CASE_STAGES.find((stage) => stage.segment === segment) ?? null;
}

/** Posição da etapa no workflow, contada de 1 — é o número mostrado ao advogado. */
export function stageNumber(module: ModuleName): number {
  return stageIndex(module) + 1;
}

/**
 * Nome de exibição de um módulo do backend. Ponto único de tradução
 * `ModuleName` → rótulo: nenhuma tela deve montar esse texto por conta
 * própria, para o nome de uma etapa nunca divergir entre a lista, a linha do
 * tempo e a visão geral do caso.
 */
export function stageLabel(module: ModuleName): string {
  return CASE_STAGES.find((stage) => stage.module === module)?.label ?? module;
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

export type StageProgress = "done" | "current" | "locked";

/** Situação de uma etapa em relação à etapa atual do caso — base visual da linha do tempo. */
export function stageProgress(currentModule: ModuleName, stage: CaseStage): StageProgress {
  const distance = stageIndex(stage.module) - stageIndex(currentModule);
  if (distance < 0) return "done";
  if (distance === 0) return "current";
  return "locked";
}

export const STAGE_PROGRESS_LABELS: Record<StageProgress, string> = {
  done: "Concluída",
  current: "Etapa atual",
  locked: "Bloqueada",
};

/**
 * O que o advogado precisa fazer para o caso sair da etapa em que está.
 * É texto de orientação, nunca de decisão: quem move a etapa é sempre uma
 * ação humana confirmada pelo backend (CLAUDE.md, seção 2).
 */
export interface StageGuidance {
  stage: CaseStage;
  /** "Etapa 2 de 6 · Evidências" — para a fase atual nunca ficar implícita. */
  position: string;
  /** O que fazer agora, em uma frase de ação. */
  title: string;
  /** Como essa ação faz o caso avançar. */
  description: string;
  /** Rótulo do botão que leva à aba da etapa. */
  ctaLabel: string;
  /** true quando a etapa ainda não tem interface própria — a aba abre vazia. */
  notImplementedYet: boolean;
}

function guidanceText(
  stage: CaseStage,
  status: CaseStatus,
): { title: string; description: string; ctaLabel: string } {
  if (status === "archived") {
    return {
      title: "Caso arquivado",
      description:
        "Nenhuma etapa avança enquanto o caso estiver arquivado. Reabrir o caso é uma decisão sua.",
      ctaLabel: `Abrir ${stage.label}`,
    };
  }
  if (status === "completed") {
    return {
      title: "Caso concluído",
      description: "O workflow chegou ao fim. As etapas seguem consultáveis para revisão.",
      ctaLabel: `Abrir ${stage.label}`,
    };
  }

  switch (stage.module) {
    case "intake":
      if (status === "pending_approval") {
        return {
          title: "Revise a recomendação da triagem para liberar Evidências",
          description:
            "A triagem de IA classificou o caso e aguarda sua decisão: aprovar, corrigir ou devolver para complementação. É essa decisão que move o caso para Evidências — nada avança sozinho.",
          ctaLabel: "Revisar a triagem",
        };
      }
      return {
        title: "Complete a abertura do caso para liberar Evidências",
        description:
          "Na aba Abertura de caso: salve o relato inicial, rode a triagem se quiser a classificação assistida e conclua a abertura. Evidências destrava quando o backend registra essa conclusão.",
        ctaLabel: "Abrir a etapa Abertura de caso",
      };
    case "evidence":
      if (status === "pending_approval") {
        return {
          title: "Valide o inventário probatório para o caso seguir",
          description:
            "A análise das evidências está pronta e aguarda validação humana. Aprovar, corrigir ou devolver é o que faz o caso sair de Evidências.",
          ctaLabel: "Revisar as evidências",
        };
      }
      return {
        title: "Anexe e valide as evidências do caso",
        description:
          "Na aba Evidências: envie os arquivos, acompanhe o processamento, confira as extrações e valide o inventário probatório. Nada segue adiante sem a sua validação.",
        ctaLabel: "Abrir a etapa Evidências",
      };
    default:
      return {
        title: `A etapa ${stage.label} ainda não está disponível no produto`,
        description:
          "O caso está registrado nesta etapa do workflow, mas o módulo correspondente ainda não foi implementado — a aba abre vazia de propósito, sem simular conteúdo jurídico.",
        ctaLabel: `Abrir ${stage.label}`,
      };
  }
}

/**
 * Orientação de próxima ação para um caso, derivada só de `current_module` e
 * `status` (ambos definidos pelo backend).
 *
 * Args:
 *   caseData: Caso carregado do backend.
 *
 * Returns:
 *   Onde o caso está, o que fazer agora e para onde o botão deve levar.
 */
export function stageGuidance(caseData: Pick<Case, "current_module" | "status">): StageGuidance {
  const stage = stageFor(caseData.current_module);
  const { title, description, ctaLabel } = guidanceText(stage, caseData.status);
  return {
    stage,
    position: `Etapa ${stageNumber(stage.module)} de ${CASE_STAGES.length} · ${stage.label}`,
    title,
    description,
    ctaLabel,
    notImplementedYet: !IMPLEMENTED_MODULES.has(stage.module),
  };
}
