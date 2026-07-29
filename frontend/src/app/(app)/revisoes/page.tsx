import { EmptyState } from "@/components/ui/EmptyState";

export default function RevisoesPendentesPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Revisões pendentes</h1>
      <EmptyState
        title="Fila de revisão ainda não está disponível"
        description="A lista de outputs de IA aguardando aprovação humana (CLAUDE.md, seção 2) ainda não foi implementada no backend."
      />
    </div>
  );
}
