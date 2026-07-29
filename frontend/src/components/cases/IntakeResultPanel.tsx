"use client";

import { CaseDocumentChecklist } from "@/components/cases/CaseDocumentChecklist";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HumanReviewNotice } from "@/components/ui/HumanReviewNotice";
import { LoadingState } from "@/components/ui/LoadingState";
import {
  CASE_AREA_LABELS,
  FRAUD_TYPE_LABELS,
  INTAKE_OUTCOME_LABELS,
  URGENCY_LABELS,
} from "@/lib/caseLabels";
import type { IntakeResult } from "@/types/api";

interface IntakeResultPanelProps {
  result: IntakeResult | null;
  isLoading: boolean;
  error: string | null;
  notRunYet: boolean;
  onRetry: () => void;
  caseId: string;
  canWrite: boolean;
  checklistVersion: number;
}

/**
 * Painel de resultado da triagem (docs/roadmap_mvp_squad_digital.md, 2.6).
 * Toda saída vem literalmente de IntakeResultResponse
 * (backend/app/models/schemas/intake.py) — nada aqui é inventado. Duas
 * lacunas conhecidas do backend, documentadas em vez de preenchidas com
 * dado fabricado: não há "fatos extraídos"/resumo do caso exposto pela API
 * (o `case_summary` da triagem só existe hasheado em audit_logs — ver
 * docs/frontend_case_screens.md) e não há "próximo módulo" como campo
 * literal — é inferido de `intake_outcome` porque
 * `review_intake_recommendation` sempre avança para "evidence" quando a
 * decisão é approve/correct.
 */
export function IntakeResultPanel({
  result,
  isLoading,
  error,
  notRunYet,
  onRetry,
  caseId,
  canWrite,
  checklistVersion,
}: IntakeResultPanelProps) {
  if (isLoading) return <LoadingState label="Carregando resultado da triagem..." />;
  if (notRunYet) {
    return (
      <EmptyState
        title="A triagem ainda não foi executada"
        description="Salve o relato inicial e clique em 'Executar triagem' para gerar uma classificação preliminar."
      />
    );
  }
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (!result) return null;

  const isOutOfScope = result.intake_outcome === "blocked";
  const isAwaitingInformation = result.intake_outcome === "awaiting_information";
  const nextModuleRecommended = result.intake_outcome === "awaiting_human_review";

  return (
    <div className="space-y-4">
      <HumanReviewNotice />

      {result.intake_outcome && (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <span className="font-medium">Situação da triagem:</span>{" "}
          {INTAKE_OUTCOME_LABELS[result.intake_outcome]}
        </p>
      )}

      {isOutOfScope && result.out_of_scope_reason && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <span className="font-medium">Fora do escopo do Squad Digital:</span>{" "}
          {result.out_of_scope_reason} Este caso precisa ser encaminhado manualmente — nenhum outro
          fluxo é acionado automaticamente.
        </p>
      )}

      <dl className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium uppercase text-slate-500">Plataforma provável</dt>
          <dd className="mt-1 text-sm text-slate-900">{result.platform}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase text-slate-500">Modalidade provável</dt>
          <dd className="mt-1 text-sm text-slate-900">
            {FRAUD_TYPE_LABELS[result.fraud_type] ?? result.fraud_type}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase text-slate-500">Urgência</dt>
          <dd className="mt-1 text-sm text-slate-900">
            {URGENCY_LABELS[result.urgency] ?? result.urgency}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase text-slate-500">Área / Matéria</dt>
          <dd className="mt-1 text-sm text-slate-900">
            {result.area ? (CASE_AREA_LABELS[result.area] ?? result.area) : "—"}
            {result.matter ? ` — ${result.matter}` : ""}
          </dd>
        </div>
      </dl>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <p className="text-xs font-medium uppercase text-slate-500">Informações pendentes</p>
        {result.missing_information.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">Nenhuma pendência apontada pela triagem.</p>
        ) : (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-800">
            {result.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </div>

      {isAwaitingInformation && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          A triagem não teve dados suficientes para concluir a classificação. Complemente o relato
          inicial e execute a triagem novamente.
        </p>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <p className="text-xs font-medium uppercase text-slate-500">Checklist de documentos</p>
        <div className="mt-2">
          <CaseDocumentChecklist
            key={checklistVersion}
            caseId={caseId}
            canWrite={canWrite}
            suggestedFromTriage={result.documents_requested}
          />
        </div>
      </div>

      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
        <span className="font-medium">Próximo módulo recomendado:</span>{" "}
        {nextModuleRecommended
          ? "Evidências — liberado após aprovação humana da triagem."
          : "Nenhum — o caso permanece em Intake até a pendência acima ser resolvida."}
      </p>
    </div>
  );
}
