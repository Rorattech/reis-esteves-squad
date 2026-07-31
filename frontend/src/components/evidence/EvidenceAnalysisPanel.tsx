"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HumanReviewNotice } from "@/components/ui/HumanReviewNotice";
import { LoadingState } from "@/components/ui/LoadingState";
import {
  FINDING_CATEGORY_LABELS,
  FINDING_RELEVANCE_LABELS,
} from "@/lib/caseLabels";
import { api, ApiError } from "@/services/api";
import type { EvidenceAnalysisResult, EvidenceFinding } from "@/types/api";

const CATEGORY_STYLES: Record<EvidenceFinding["category"], string> = {
  fact: "bg-emerald-100 text-emerald-800",
  inference: "bg-blue-100 text-blue-800",
  missing_info: "bg-amber-100 text-amber-800",
};

interface EvidenceAnalysisPanelProps {
  caseId: string;
  analysis: EvidenceAnalysisResult | null;
  isLoading: boolean;
  error: string | null;
  notRunYet: boolean;
  canWrite: boolean;
  hasEvidence: boolean;
  onRetry: () => void;
  onChanged: () => void;
}

function FindingCard({ finding }: { finding: EvidenceFinding }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CATEGORY_STYLES[finding.category]}`}
        >
          {FINDING_CATEGORY_LABELS[finding.category]}
        </span>
        <span className="text-xs text-slate-500">
          Relevância {FINDING_RELEVANCE_LABELS[finding.relevance]} · confiança{" "}
          {Math.round(finding.confidence * 100)}% · agente {finding.agent}
        </span>
        {finding.status === "DRAFT_PENDING_REVIEW" && (
          <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
            Pendente de revisão
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-slate-900">{finding.summary}</p>
      <p className="mt-1 text-xs text-slate-600">
        <span className="font-medium">Uso sugerido:</span> {finding.suggested_use}
      </p>
      {finding.gaps.length > 0 && (
        <p className="mt-1 text-xs text-amber-700">
          <span className="font-medium">Lacunas:</span> {finding.gaps.join("; ")}
        </p>
      )}
      <p className="mt-1 text-xs text-slate-400">
        {finding.evidence_id
          ? `Origem: evidência ${finding.evidence_id.slice(0, 8)}…`
          : "Sem evidência de origem — aponta o que está faltando."}
      </p>
    </li>
  );
}

/**
 * Inventário probatório + leitura técnica (roadmap 3.4) com a decisão humana
 * obrigatória (roadmap 3.3): aprovar (avança para pesquisa) ou devolver com
 * justificativa. Nada aqui é decisão jurídica autônoma — todo conteúdo dos
 * agentes chega DRAFT_PENDING_REVIEW e assim permanece até a ação do
 * advogado.
 */
export function EvidenceAnalysisPanel({
  caseId,
  analysis,
  isLoading,
  error,
  notRunYet,
  canWrite,
  hasEvidence,
  onRetry,
  onChanged,
}: EvidenceAnalysisPanelProps) {
  const [isRunning, setIsRunning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmingApprove, setConfirmingApprove] = useState(false);
  const [returnNotes, setReturnNotes] = useState("");
  const [showReturnForm, setShowReturnForm] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);

  async function runAnalysis() {
    setActionError(null);
    setIsRunning(true);
    try {
      await api.runEvidenceAnalysis(caseId);
      onChanged();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Não foi possível executar a análise.",
      );
    } finally {
      setIsRunning(false);
    }
  }

  async function review(decision: "approve" | "return_for_information") {
    setActionError(null);
    setIsReviewing(true);
    try {
      await api.reviewEvidenceAnalysis(caseId, {
        decision,
        notes: decision === "return_for_information" ? returnNotes : undefined,
      });
      setShowReturnForm(false);
      setReturnNotes("");
      onChanged();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Não foi possível registrar a revisão.",
      );
    } finally {
      setIsReviewing(false);
    }
  }

  if (isLoading) return <LoadingState label="Carregando análise de evidências..." />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;

  const runButton = canWrite && (
    <button
      type="button"
      disabled={isRunning || !hasEvidence}
      onClick={runAnalysis}
      className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
    >
      {isRunning
        ? "Analisando evidências..."
        : notRunYet
          ? "Executar análise de evidências"
          : "Reexecutar análise"}
    </button>
  );

  if (notRunYet || !analysis) {
    return (
      <div className="space-y-3">
        {actionError && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
        )}
        <EmptyState
          title="A análise de evidências ainda não foi executada"
          description={
            hasEvidence
              ? "Os agentes documental e especialista montam o inventário probatório a partir dos arquivos anexados — sempre como recomendação revisável."
              : "Anexe ao menos uma evidência para liberar a análise."
          }
          action={runButton || undefined}
        />
      </div>
    );
  }

  const pendingReview =
    analysis.evidence_outcome === "awaiting_human_review" &&
    analysis.human_review_required &&
    analysis.current_module === "evidence";

  return (
    <div className="space-y-4">
      <HumanReviewNotice />
      {actionError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          {analysis.findings.length} achado(s) no inventário probatório.
        </p>
        {runButton}
      </div>

      {analysis.findings.length === 0 ? (
        <EmptyState title="A análise não registrou achados" />
      ) : (
        <ul className="space-y-2">
          {analysis.findings.map((finding) => (
            <FindingCard key={finding.id} finding={finding} />
          ))}
        </ul>
      )}

      {analysis.specialist_assessment && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-slate-900">
            Leitura técnica da plataforma
            <span className="ml-2 inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
              Rascunho — requer revisão
            </span>
          </h3>
          <p className="mt-2 text-sm text-slate-700">
            {analysis.specialist_assessment.platform_context}
          </p>
          {analysis.specialist_assessment.platform_failure && (
            <p className="mt-2 text-sm text-slate-700">
              <span className="font-medium">Onde a plataforma falhou:</span>{" "}
              {analysis.specialist_assessment.platform_failure}
            </p>
          )}
          {analysis.specialist_assessment.report_mechanism_analysis && (
            <p className="mt-2 text-sm text-slate-700">
              <span className="font-medium">Mecanismo de denúncia:</span>{" "}
              {analysis.specialist_assessment.report_mechanism_analysis}
            </p>
          )}
          {analysis.specialist_assessment.preservation_recommendations.length > 0 && (
            <div className="mt-2">
              <p className="text-sm font-medium text-slate-700">Preservação recomendada:</p>
              <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
                {analysis.specialist_assessment.preservation_recommendations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {analysis.specialist_assessment.hypotheses.length > 0 && (
            <div className="mt-2">
              <p className="text-sm font-medium text-slate-700">Hipóteses (não conclusões):</p>
              <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
                {analysis.specialist_assessment.hypotheses.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {pendingReview && canWrite && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="text-sm font-semibold text-amber-900">Decisão do advogado</h3>
          <p className="mt-1 text-sm text-amber-800">
            Aprovar encaminha o caso para a pesquisa jurídica; devolver mantém o caso em
            evidências aguardando complementação.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isReviewing}
              onClick={() => setConfirmingApprove(true)}
              className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-60"
            >
              Aprovar inventário
            </button>
            <button
              type="button"
              disabled={isReviewing}
              onClick={() => setShowReturnForm((value) => !value)}
              className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-60"
            >
              Devolver para complementação
            </button>
          </div>
          {showReturnForm && (
            <form
              className="mt-3 space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                review("return_for_information");
              }}
            >
              <label htmlFor="evidence-return-notes" className="block text-sm text-amber-900">
                Justificativa (obrigatória para devolução)
              </label>
              <textarea
                id="evidence-return-notes"
                value={returnNotes}
                onChange={(event) => setReturnNotes(event.target.value)}
                rows={3}
                className="w-full rounded-md border border-amber-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={isReviewing || returnNotes.trim().length === 0}
                className="rounded-md bg-amber-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-60"
              >
                {isReviewing ? "Registrando..." : "Confirmar devolução"}
              </button>
            </form>
          )}
        </div>
      )}

      {!pendingReview && analysis.current_module !== "evidence" && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Inventário aprovado — o caso avançou para a pesquisa jurídica.
        </p>
      )}

      <ConfirmDialog
        open={confirmingApprove}
        title="Aprovar o inventário probatório?"
        description="A aprovação é registrada em auditoria com sua identificação e encaminha o caso para o módulo de pesquisa jurídica."
        confirmLabel="Aprovar e avançar"
        onConfirm={() => {
          setConfirmingApprove(false);
          review("approve");
        }}
        onCancel={() => setConfirmingApprove(false)}
      />
    </div>
  );
}
