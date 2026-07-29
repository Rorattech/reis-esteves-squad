"use client";

import Link from "next/link";

import { CASE_STAGES, isStageUnlocked } from "@/lib/caseStages";
import type { ModuleName } from "@/types/api";

interface CaseTimelineProps {
  basePath: string;
  currentModule: ModuleName;
  activeSegment: string;
}

/**
 * Linha do tempo das 6 etapas do workflow (docs/roadmap_mvp_squad_digital.md,
 * 2.5): Intake → Evidências → Pesquisa → Estratégia → Minuta → Revisão.
 *
 * Etapas além de `currentModule` (Case.current_module, definido só pelo
 * backend — ver POST .../intake/review) aparecem bloqueadas e não são um
 * link: a interface nunca simula avanço de etapa por conta própria
 * (CLAUDE.md, seção 16).
 */
export function CaseTimeline({ basePath, currentModule, activeSegment }: CaseTimelineProps) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2" aria-label="Etapas do caso">
      {CASE_STAGES.map((stage, index) => {
        const unlocked = isStageUnlocked(currentModule, stage);
        const isCurrent = stage.module === currentModule;
        const isActiveTab = stage.segment === activeSegment;

        return (
          <li key={stage.module} className="flex items-center">
            {index > 0 && <span className="mx-1 h-px w-4 bg-slate-300" aria-hidden="true" />}
            {unlocked ? (
              <Link
                href={`${basePath}/${stage.segment}`}
                aria-current={isActiveTab ? "step" : undefined}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  isActiveTab
                    ? "border-slate-900 bg-slate-900 text-white"
                    : isCurrent
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {stage.label}
              </Link>
            ) : (
              <span
                title="Ainda não liberada — o caso precisa avançar até esta etapa."
                aria-disabled="true"
                className="flex items-center gap-1 rounded-full border border-dashed border-slate-200 px-3 py-1 text-xs font-medium text-slate-400"
              >
                <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3">
                  <path
                    fillRule="evenodd"
                    d="M10 1a4 4 0 0 0-4 4v2H5a1 1 0 0 0-1 1v9a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-9a1 1 0 0 0-1-1h-1V5a4 4 0 0 0-4-4Zm2 6V5a2 2 0 1 0-4 0v2h4Z"
                    clipRule="evenodd"
                  />
                </svg>
                {stage.label}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
