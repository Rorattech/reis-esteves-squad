"use client";

import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuditLog } from "@/hooks/useAuditLog";
import { AUDIT_ACTOR_LABELS } from "@/lib/caseLabels";

/**
 * Histórico de auditoria do caso (GET .../audit-log) — toda mutação de
 * intake/checklist/revisão humana passa por aqui (CLAUDE.md, seção 10).
 * Usado na aba Histórico e, de forma resumida, na aba Intake, para que toda
 * revisão humana fique visível (docs/roadmap_mvp_squad_digital.md, 2.6).
 */
export function AuditLogTimeline({ caseId, limit }: { caseId: string; limit?: number }) {
  const { entries, isLoading, error, forbidden, reload } = useAuditLog(caseId);

  if (isLoading) return <LoadingState label="Carregando histórico..." />;
  if (forbidden) {
    return (
      <AccessDeniedState message="Seu papel não tem acesso ao histórico de auditoria deste caso." />
    );
  }
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (entries.length === 0) {
    return (
      <EmptyState
        title="Nenhuma ação registrada ainda"
        description="Assim que o relato, a triagem ou uma revisão humana acontecerem, aparecem aqui."
      />
    );
  }

  const visibleEntries = limit ? entries.slice(-limit).reverse() : [...entries].reverse();

  return (
    <ol className="space-y-3">
      {visibleEntries.map((entry) => {
        const decision = typeof entry.metadata.decision === "string" ? entry.metadata.decision : null;
        const notes = typeof entry.metadata.notes === "string" ? entry.metadata.notes : null;
        return (
          <li
            key={entry.id}
            className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-slate-900">{entry.action}</p>
              <time className="text-xs text-slate-500" dateTime={entry.created_at}>
                {new Date(entry.created_at).toLocaleString("pt-BR")}
              </time>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {AUDIT_ACTOR_LABELS[entry.actor]} · {entry.actor_id}
            </p>
            {decision && (
              <p className="mt-1 text-xs text-slate-600">
                Decisão: <span className="font-medium">{decision}</span>
              </p>
            )}
            {notes && <p className="mt-1 text-sm text-slate-700">&ldquo;{notes}&rdquo;</p>}
          </li>
        );
      })}
    </ol>
  );
}
