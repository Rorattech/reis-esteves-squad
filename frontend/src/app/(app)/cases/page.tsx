"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import { useCases } from "@/hooks/useCases";
import { CASE_STATUS_LABELS, FRAUD_TYPE_LABELS } from "@/lib/caseLabels";
import { CASE_STAGES } from "@/lib/caseStages";
import { canWriteCase } from "@/lib/roles";
import type { CaseStatus } from "@/types/api";

const STATUS_FILTER_OPTIONS: { value: CaseStatus | "all"; label: string }[] = [
  { value: "all", label: "Todos os status" },
  ...(Object.entries(CASE_STATUS_LABELS) as [CaseStatus, string][]).map(([value, label]) => ({
    value,
    label,
  })),
];

export default function CasesPage() {
  const { cases, isLoading, error, reload } = useCases();
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<CaseStatus | "all">("all");

  const canCreateCase = canWriteCase(user);

  // Filtro e busca são só do lado do cliente, sobre a lista já carregada —
  // GET /cases não aceita parâmetros de busca/filtro hoje (backend/app/api/v1/cases.py).
  const filteredCases = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return cases.filter((item) => {
      const matchesStatus = statusFilter === "all" || item.status === statusFilter;
      const matchesSearch =
        normalizedSearch.length === 0 ||
        item.platform.toLowerCase().includes(normalizedSearch) ||
        (item.matter ?? "").toLowerCase().includes(normalizedSearch);
      return matchesStatus && matchesSearch;
    });
  }, [cases, search, statusFilter]);

  const newCaseButton = canCreateCase ? (
    <Link
      href="/cases/new"
      className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
    >
      Novo caso
    </Link>
  ) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Casos</h1>
        {newCaseButton}
      </div>

      {isLoading && <LoadingState label="Carregando casos..." />}

      {!isLoading && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !error && cases.length === 0 && (
        <EmptyState
          title="Nenhum caso ainda"
          description="Quando um caso for aberto para este escritório, ele aparece aqui."
          action={
            canCreateCase ? (
              <Link
                href="/cases/new"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
              >
                Criar caso
              </Link>
            ) : undefined
          }
        />
      )}

      {!isLoading && !error && cases.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por plataforma ou matéria..."
              aria-label="Buscar casos"
              className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as CaseStatus | "all")}
              aria-label="Filtrar por status"
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
            >
              {STATUS_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {filteredCases.length === 0 ? (
            <EmptyState
              title="Nenhum caso encontrado"
              description="Ajuste a busca ou o filtro de status para ver outros casos."
            />
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Plataforma</th>
                    <th className="px-4 py-3 font-medium">Cliente</th>
                    <th className="px-4 py-3 font-medium">Modalidade</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Etapa atual</th>
                    <th className="px-4 py-3 font-medium">Última atualização</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredCases.map((item) => {
                    const stage = CASE_STAGES.find((s) => s.module === item.current_module);
                    return (
                      <tr key={item.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <Link
                            href={`/cases/${item.id}`}
                            className="font-medium text-slate-900 hover:underline"
                          >
                            {item.platform}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-slate-500">{item.client_id ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-600">
                          {FRAUD_TYPE_LABELS[item.fraud_type] ?? item.fraud_type}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={item.status} />
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {stage?.label ?? item.current_module}
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {new Date(item.updated_at).toLocaleDateString("pt-BR")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
