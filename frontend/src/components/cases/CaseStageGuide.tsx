"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { stageGuidance } from "@/lib/caseStages";
import type { Case } from "@/types/api";

interface CaseStageGuideProps {
  caseData: Case;
  basePath: string;
  /**
   * false quando o advogado já está na aba da etapa atual — o botão sairia
   * para a página onde ele já está, então só a orientação é mostrada.
   */
  showCta?: boolean;
}

/**
 * Orientação fixa de próxima ação do caso (CLAUDE.md, seção 16: pendências
 * nunca ficam escondidas). Responde às duas perguntas que a linha do tempo
 * sozinha não respondia — "em que fase o caso está?" e "o que eu faço para
 * passar de fase?" — e leva para a aba onde a ação existe de verdade.
 *
 * Não decide nada: o texto vem de `Case.current_module` + `Case.status`, os
 * dois definidos pelo backend, e nenhuma etapa muda por abrir esta tela.
 */
export function CaseStageGuide({ caseData, basePath, showCta = true }: CaseStageGuideProps) {
  const guidance = stageGuidance(caseData);

  return (
    <section
      aria-labelledby="case-stage-guide-title"
      className="rounded-lg border border-blue-200 bg-blue-50 p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
        {guidance.position}
      </p>
      <h2 id="case-stage-guide-title" className="mt-1 text-sm font-semibold text-slate-900">
        {guidance.title}
      </h2>
      <p className="mt-1 text-sm text-slate-700">{guidance.description}</p>

      {showCta && (
        <Link
          href={`${basePath}/${guidance.stage.segment}`}
          className={`mt-3 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${
            guidance.notImplementedYet
              ? "border border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
              : "bg-slate-900 text-white hover:bg-slate-800"
          }`}
        >
          {guidance.ctaLabel}
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </Link>
      )}
    </section>
  );
}
