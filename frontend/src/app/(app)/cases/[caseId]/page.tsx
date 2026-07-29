"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useCase } from "@/hooks/useCase";
import { FRAUD_TYPE_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";

export default function CaseOverviewPage() {
  const params = useParams<{ caseId: string }>();
  const { case: caseData, isLoading, error, reload } = useCase(params.caseId);

  if (isLoading) return <LoadingState label="Carregando visão geral..." />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!caseData) return null;

  return (
    <dl className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-2">
      <div>
        <dt className="text-xs font-medium uppercase text-slate-500">Plataforma</dt>
        <dd className="mt-1 text-sm text-slate-900">{caseData.platform}</dd>
      </div>
      <div>
        <dt className="text-xs font-medium uppercase text-slate-500">Modalidade</dt>
        <dd className="mt-1 text-sm text-slate-900">
          {FRAUD_TYPE_LABELS[caseData.fraud_type] ?? caseData.fraud_type}
        </dd>
      </div>
      <div>
        <dt className="text-xs font-medium uppercase text-slate-500">Urgência</dt>
        <dd className="mt-1 text-sm text-slate-900">
          {URGENCY_LABELS[caseData.urgency] ?? caseData.urgency}
        </dd>
      </div>
      <div>
        <dt className="text-xs font-medium uppercase text-slate-500">Última atualização</dt>
        <dd className="mt-1 text-sm text-slate-900">
          {new Date(caseData.updated_at).toLocaleString("pt-BR")}
        </dd>
      </div>
    </dl>
  );
}
