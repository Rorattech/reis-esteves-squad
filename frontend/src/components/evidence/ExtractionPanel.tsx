"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { api, ApiError } from "@/services/api";
import type { EvidenceExtraction } from "@/types/api";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

interface ExtractionPanelProps {
  caseId: string;
  evidenceId: string;
  extractions: EvidenceExtraction[];
  canWrite: boolean;
  onChanged: () => void;
}

/**
 * Conteúdo extraído + validação humana (roadmap 3.5). O texto derivado nunca
 * é editável nem apresentado como prova perfeita: confiança e limitações
 * aparecem sempre, e a correção humana cria um registro auditado — jamais
 * substitui o texto ou o original.
 */
export function ExtractionPanel({
  caseId,
  evidenceId,
  extractions,
  canWrite,
  onChanged,
}: ExtractionPanelProps) {
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submitReview(
    extractionId: string,
    verdict: "confirmed" | "extraction_error",
  ) {
    setActionError(null);
    setIsSubmitting(true);
    try {
      await api.reviewEvidenceExtraction(caseId, evidenceId, extractionId, {
        verdict,
        note: verdict === "extraction_error" ? note : undefined,
      });
      setReviewingId(null);
      setNote("");
      onChanged();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível registrar a revisão.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (extractions.length === 0) {
    return (
      <EmptyState
        title="Nenhuma extração registrada ainda"
        description="O pipeline roda automaticamente após o upload. Se o arquivo acabou de ser enviado, recarregue em instantes — ou dispare o reprocessamento."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        <span className="font-semibold">Conteúdo derivado.</span> OCR e transcrição são leituras
        automáticas do original, sujeitas a erro — confira sempre contra o arquivo original antes
        de usar como prova.
      </div>
      {actionError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
      )}

      {extractions.map((extraction) => (
        <div key={extraction.id} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-500">
              {formatDate(extraction.created_at)} · {extraction.tool_name}{" "}
              {extraction.tool_version} · método {extraction.kind}
            </p>
            {extraction.outcome === "succeeded" ? (
              <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                Extração concluída
                {extraction.confidence !== null &&
                  ` — confiança ${Math.round(extraction.confidence * 100)}%`}
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                Extração falhou
              </span>
            )}
          </div>

          {extraction.limitations && (
            <p className="mt-2 text-xs text-slate-500">{extraction.limitations}</p>
          )}

          {extraction.outcome === "succeeded" ? (
            <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 font-mono text-xs text-slate-800">
              {extraction.extracted_text || "(nenhum texto identificado no arquivo)"}
            </pre>
          ) : (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {extraction.error_message ?? "Falha na extração."} O arquivo original permanece
              intacto — você pode disparar o reprocessamento.
            </p>
          )}

          {extraction.reviews.length > 0 && (
            <ul className="mt-3 space-y-1" aria-label="Revisões humanas desta extração">
              {extraction.reviews.map((review) => (
                <li
                  key={review.id}
                  className={
                    review.verdict === "confirmed"
                      ? "rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
                      : "rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800"
                  }
                >
                  {review.verdict === "confirmed"
                    ? "Conferido contra o original"
                    : "Erro de extração apontado"}
                  {review.note && ` — "${review.note}"`} ({formatDate(review.created_at)})
                </li>
              ))}
            </ul>
          )}

          {canWrite && extraction.outcome === "succeeded" && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => submitReview(extraction.id, "confirmed")}
                  className="rounded-md border border-emerald-300 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-50 disabled:opacity-60"
                >
                  Confirmar conteúdo
                </button>
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() =>
                    setReviewingId(reviewingId === extraction.id ? null : extraction.id)
                  }
                  className="rounded-md border border-amber-300 px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60"
                >
                  Apontar erro de extração
                </button>
              </div>
              {reviewingId === extraction.id && (
                <form
                  className="mt-2 space-y-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    submitReview(extraction.id, "extraction_error");
                  }}
                >
                  <label
                    htmlFor={`extraction-note-${extraction.id}`}
                    className="block text-xs text-slate-600"
                  >
                    Descreva o erro (a correção fica registrada — o texto extraído e o original
                    não são alterados)
                  </label>
                  <textarea
                    id={`extraction-note-${extraction.id}`}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    rows={2}
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={isSubmitting || note.trim().length === 0}
                    className="rounded-md bg-amber-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-60"
                  >
                    {isSubmitting ? "Registrando..." : "Registrar erro"}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
