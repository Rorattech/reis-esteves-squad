"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { CaseTimeline } from "@/components/cases/CaseTimeline";
import { ErrorState } from "@/components/ui/ErrorState";
import { HumanReviewNotice } from "@/components/ui/HumanReviewNotice";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useCase } from "@/hooks/useCase";

const META_TABS = [
  { segment: "", label: "Visão geral" },
  { segment: "historico", label: "Histórico" },
];

export default function CaseLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ caseId: string }>();
  const pathname = usePathname();
  const { case: caseData, isLoading, error, notFound, reload } = useCase(params.caseId);
  const basePath = `/cases/${params.caseId}`;
  const activeSegment = pathname.slice(basePath.length).replace(/^\//, "");

  return (
    <div className="space-y-4">
      <Link href="/cases" className="text-sm text-slate-500 hover:text-slate-700">
        ← Voltar para Casos
      </Link>

      {isLoading && <LoadingState label="Carregando caso..." />}
      {!isLoading && notFound && <AccessDeniedState />}
      {!isLoading && !notFound && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !notFound && !error && caseData && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{caseData.platform}</h1>
              <p className="text-sm text-slate-500">
                Caso aberto em {new Date(caseData.created_at).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <StatusBadge status={caseData.status} />
          </div>

          <HumanReviewNotice />

          <div className="space-y-3 border-b border-slate-200 pb-3">
            <CaseTimeline
              basePath={basePath}
              currentModule={caseData.current_module}
              activeSegment={activeSegment}
            />
            <nav className="flex flex-wrap gap-4">
              {META_TABS.map((tab) => {
                const href = tab.segment ? `${basePath}/${tab.segment}` : basePath;
                const active = pathname === href;
                return (
                  <Link
                    key={tab.label}
                    href={href}
                    className={`text-sm font-medium ${
                      active ? "text-slate-900 underline" : "text-slate-500 hover:text-slate-700"
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
