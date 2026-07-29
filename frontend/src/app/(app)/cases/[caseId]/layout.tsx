"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ErrorState } from "@/components/ui/ErrorState";
import { HumanReviewNotice } from "@/components/ui/HumanReviewNotice";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useCase } from "@/hooks/useCase";

const TABS = [
  { segment: "", label: "Visão geral" },
  { segment: "intake", label: "Intake" },
  { segment: "evidencias", label: "Evidências" },
  { segment: "pesquisa", label: "Pesquisa" },
  { segment: "estrategia", label: "Estratégia" },
  { segment: "minuta", label: "Minuta" },
  { segment: "revisao", label: "Revisão" },
  { segment: "historico", label: "Histórico" },
];

export default function CaseLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ caseId: string }>();
  const pathname = usePathname();
  const { case: caseData, isLoading, error, reload } = useCase(params.caseId);
  const basePath = `/cases/${params.caseId}`;

  return (
    <div className="space-y-4">
      <Link href="/cases" className="text-sm text-slate-500 hover:text-slate-700">
        ← Voltar para Casos
      </Link>

      {isLoading && <LoadingState label="Carregando caso..." />}
      {!isLoading && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !error && caseData && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{caseData.platform}</h1>
              <p className="text-sm text-slate-500">
                Caso aberto em {new Date(caseData.created_at).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <StatusBadge status={caseData.status} />
          </div>

          <HumanReviewNotice />

          <div className="border-b border-slate-200">
            <nav className="-mb-px flex flex-wrap gap-4">
              {TABS.map((tab) => {
                const href = tab.segment ? `${basePath}/${tab.segment}` : basePath;
                const active = pathname === href;
                return (
                  <Link
                    key={tab.label}
                    href={href}
                    className={`border-b-2 px-1 pb-2 text-sm font-medium ${
                      active
                        ? "border-slate-900 text-slate-900"
                        : "border-transparent text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div>{children}</div>
        </>
      )}
    </div>
  );
}
