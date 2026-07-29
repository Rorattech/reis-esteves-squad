import type { CaseStatus } from "@/types/api";

const STATUS_LABELS: Record<CaseStatus, string> = {
  draft: "Rascunho",
  in_progress: "Em andamento",
  pending_approval: "Aguardando aprovação",
  approved: "Aprovado",
  completed: "Concluído",
  archived: "Arquivado",
};

const STATUS_STYLES: Record<CaseStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-700",
  completed: "bg-green-100 text-green-700",
  archived: "bg-slate-200 text-slate-500",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
