"use client";

import Link from "next/link";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useCases } from "@/hooks/useCases";
import { FRAUD_TYPE_LABELS } from "@/lib/caseLabels";

export default function CasesPage() {
  const { cases, isLoading, error, reload } = useCases();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Casos</h1>

      {isLoading && <LoadingState label="Carregando casos..." />}

      {!isLoading && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !error && cases.length === 0 && (
        <EmptyState
          title="Nenhum caso ainda"
          description="Quando um caso for aberto para este escritório, ele aparece aqui."
        />
      )}

      {!isLoading && !error && cases.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Plataforma</th>
                <th className="px-4 py-3 font-medium">Modalidade</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Aberto em</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cases.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/cases/${item.id}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {item.platform}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {FRAUD_TYPE_LABELS[item.fraud_type] ?? item.fraud_type}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(item.created_at).toLocaleDateString("pt-BR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
