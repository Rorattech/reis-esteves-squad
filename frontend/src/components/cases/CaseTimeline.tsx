"use client";

import Link from "next/link";

import {
  CASE_STAGES,
  STAGE_PROGRESS_LABELS,
  isStageUnlocked,
  stageLabel,
  stageProgress,
  type StageProgress,
} from "@/lib/caseStages";
import type { ModuleName } from "@/types/api";

interface CaseTimelineProps {
  basePath: string;
  currentModule: ModuleName;
  activeSegment: string;
}

/** Estilos por situação da etapa — cor comunica progresso, contorno comunica "aba aberta". */
const CIRCLE_STYLES: Record<StageProgress, string> = {
  done: "border-emerald-600 bg-emerald-600 text-white",
  current: "border-blue-600 bg-blue-600 text-white",
  locked: "border-slate-200 bg-slate-100 text-slate-400",
};

const CONTAINER_STYLES: Record<StageProgress, string> = {
  done: "border-slate-200 bg-white hover:bg-slate-50",
  current: "border-blue-300 bg-blue-50",
  locked: "border-dashed border-slate-200 bg-slate-50",
};

const LABEL_STYLES: Record<StageProgress, string> = {
  done: "text-slate-700",
  current: "text-blue-900",
  locked: "text-slate-400",
};

const CAPTION_STYLES: Record<StageProgress, string> = {
  done: "text-emerald-700",
  current: "text-blue-700",
  locked: "text-slate-400",
};

function CheckIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
      <path
        fillRule="evenodd"
        d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 9.7a1 1 0 1 1 1.4-1.4l3.8 3.8 6.8-6.8a1 1 0 0 1 1.4 0Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3">
      <path
        fillRule="evenodd"
        d="M10 1a4 4 0 0 0-4 4v2H5a1 1 0 0 0-1 1v9a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-9a1 1 0 0 0-1-1h-1V5a4 4 0 0 0-4-4Zm2 6V5a2 2 0 1 0-4 0v2h4Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/**
 * Linha do tempo das 6 etapas do workflow (docs/roadmap_mvp_squad_digital.md,
 * 2.5): Intake → Evidências → Pesquisa → Estratégia → Minuta → Revisão.
 *
 * Cada etapa mostra explicitamente sua situação — concluída, atual ou
 * bloqueada — em número, ícone, cor e texto, para a fase do caso nunca
 * depender de o advogado interpretar um destaque sutil.
 *
 * Etapas além de `currentModule` (Case.current_module, definido só pelo
 * backend — ver POST .../intake/review e .../intake/advance) aparecem
 * bloqueadas e não são um link: a interface nunca simula avanço de etapa por
 * conta própria (CLAUDE.md, seção 16).
 */
export function CaseTimeline({ basePath, currentModule, activeSegment }: CaseTimelineProps) {
  return (
    <div className="space-y-2">
      <ol className="flex flex-wrap items-center gap-y-2" aria-label="Etapas do caso">
        {CASE_STAGES.map((stage, index) => {
          const progress = stageProgress(currentModule, stage);
          const unlocked = isStageUnlocked(currentModule, stage);
          const isActiveTab = stage.segment === activeSegment;
          const caption = STAGE_PROGRESS_LABELS[progress];

          const inner = (
            <>
              <span
                aria-hidden="true"
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${CIRCLE_STYLES[progress]}`}
              >
                {progress === "done" ? (
                  <CheckIcon />
                ) : progress === "locked" ? (
                  <LockIcon />
                ) : (
                  index + 1
                )}
              </span>
              <span className="flex flex-col text-left leading-tight">
                {unlocked ? (
                  <Link
                    href={`${basePath}/${stage.segment}`}
                    aria-current={isActiveTab ? "step" : undefined}
                    className={`text-xs font-medium hover:underline ${LABEL_STYLES[progress]}`}
                  >
                    {stage.label}
                  </Link>
                ) : (
                  <span
                    aria-disabled="true"
                    title={`Ainda não liberada — o caso está em "${stageLabel(currentModule)}".`}
                    className={`text-xs font-medium ${LABEL_STYLES[progress]}`}
                  >
                    {stage.label}
                  </span>
                )}
                <span className={`text-[10px] uppercase tracking-wide ${CAPTION_STYLES[progress]}`}>
                  {caption}
                </span>
              </span>
            </>
          );

          return (
            <li key={stage.module} className="flex items-center">
              {index > 0 && (
                <span
                  aria-hidden="true"
                  className={`mx-1 h-px w-4 ${progress === "locked" ? "bg-slate-200" : "bg-slate-400"}`}
                />
              )}
              <div
                className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${
                  CONTAINER_STYLES[progress]
                } ${isActiveTab ? "ring-2 ring-slate-900 ring-offset-1" : ""}`}
              >
                {inner}
              </div>
            </li>
          );
        })}
      </ol>

      <p className="text-xs text-slate-500">
        O caso está em <strong className="font-medium text-slate-700">{stageLabel(currentModule)}</strong>. As
        etapas seguintes destravam quando você conclui a etapa atual — a mudança de etapa é sempre
        registrada pelo backend, nunca antecipada pela tela.
      </p>
    </div>
  );
}
