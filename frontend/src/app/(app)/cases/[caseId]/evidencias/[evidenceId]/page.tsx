"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { EvidenceOriginalViewer } from "@/components/evidence/EvidenceOriginalViewer";
import { ExtractionPanel } from "@/components/evidence/ExtractionPanel";
import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";
import { useEvidenceAnalysis } from "@/hooks/useEvidenceAnalysis";
import { useEvidenceDetail } from "@/hooks/useEvidenceDetail";
import { EVIDENCE_STATUS_LABELS, FINDING_CATEGORY_LABELS } from "@/lib/caseLabels";
import { canWriteCase } from "@/lib/roles";
import { api, ApiError } from "@/services/api";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Detalhe de evidência (roadmap 3.5): metadados e cadeia de custódia,
 * original em visualização protegida, texto extraído com confiança e
 * limitações explícitas (separado visualmente do original) e a validação
 * humana da extração — que registra, nunca sobrescreve.
 */
export default function EvidenceDetailPage() {
  const params = useParams<{ caseId: string; evidenceId: string }>();
  const { caseId, evidenceId } = params;
  const { user } = useAuth();
  const canWrite = canWriteCase(user);

  const { evidence, extractions, isLoading, error, notFound, extractionsDenied, reload } =
    useEvidenceDetail(caseId, evidenceId);
  const { analysis, reload: reloadAnalysis } = useEvidenceAnalysis(caseId);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isReprocessing, setIsReprocessing] = useState(false);

  async function reprocess() {
    setActionError(null);
    setIsReprocessing(true);
    try {
      await api.processEvidence(caseId, evidenceId);
      reload();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Não foi possível reprocessar a evidência.",
      );
    } finally {
      setIsReprocessing(false);
    }
  }

  if (isLoading) return <LoadingState label="Carregando evidência..." />;
  if (notFound) return <AccessDeniedState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!evidence) return null;

  const relatedFindings =
    analysis?.findings.filter((finding) => finding.evidence_id === evidence.id) ?? [];

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={`/cases/${caseId}/evidencias`}
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← Voltar para a Central de Evidências
        </Link>
        <h2 className="mt-2 text-base font-semibold text-slate-900">
          {evidence.original_filename}
        </h2>
      </div>

      {actionError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
      )}

      <section>
        <h3 className="text-sm font-semibold text-slate-900">Metadados e custódia</h3>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Tipo</dt>
            <dd className="text-slate-900">{evidence.mime_type}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Status de processamento</dt>
            <dd className="text-slate-900">{EVIDENCE_STATUS_LABELS[evidence.status]}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Recebido em</dt>
            <dd className="text-slate-900">{formatDate(evidence.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Origem</dt>
            <dd className="text-slate-900">{evidence.origin}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs uppercase text-slate-500">Hash de integridade (SHA-256)</dt>
            <dd className="break-all font-mono text-xs text-slate-700">{evidence.sha256_hash}</dd>
          </div>
          {evidence.is_duplicate && (
            <div className="sm:col-span-2">
              <dd className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Conteúdo idêntico a outra evidência deste escritório — cada envio permanece
                registrado separadamente na cadeia de custódia.
              </dd>
            </div>
          )}
        </dl>
        <p className="mt-2 text-xs text-slate-500">
          Upload, downloads e processamentos desta evidência ficam registrados no histórico de
          auditoria do caso (aba Histórico).
        </p>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-slate-900">Arquivo original</h3>
        <p className="mt-1 text-xs text-slate-500">
          Acesso autenticado e auditado — o original nunca é alterado por OCR ou transcrição.
        </p>
        <div className="mt-3">
          <EvidenceOriginalViewer caseId={caseId} evidence={evidence} canReadOriginal={canWrite} />
        </div>
      </section>

      <section>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Conteúdo extraído (derivado)</h3>
          {canWrite && (
            <button
              type="button"
              disabled={isReprocessing || evidence.status === "processing"}
              onClick={reprocess}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {isReprocessing ? "Disparando..." : "Reprocessar extração"}
            </button>
          )}
        </div>
        <div className="mt-3">
          {extractionsDenied ? (
            <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
              Seu papel atual não tem acesso ao conteúdo extraído desta evidência.
            </p>
          ) : (
            <ExtractionPanel
              caseId={caseId}
              evidenceId={evidenceId}
              extractions={extractions}
              canWrite={canWrite}
              onChanged={() => {
                reload();
                reloadAnalysis();
              }}
            />
          )}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-slate-900">Achados ligados a esta evidência</h3>
        <p className="mt-1 text-xs text-slate-500">
          Resultado do inventário probatório dos agentes — cada achado referencia esta evidência
          como origem e permanece rascunho até revisão humana.
        </p>
        <div className="mt-3">
          {relatedFindings.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-300 px-3 py-4 text-center text-sm text-slate-500">
              Nenhum achado do inventário referencia esta evidência ainda.
            </p>
          ) : (
            <ul className="space-y-2">
              {relatedFindings.map((finding) => (
                <li key={finding.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-xs text-slate-500">
                    {FINDING_CATEGORY_LABELS[finding.category]} · confiança{" "}
                    {Math.round(finding.confidence * 100)}% · {finding.status}
                  </p>
                  <p className="mt-1 text-sm text-slate-900">{finding.summary}</p>
                  <p className="mt-1 text-xs text-slate-600">{finding.suggested_use}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
