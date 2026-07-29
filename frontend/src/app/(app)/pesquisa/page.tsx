import { EmptyState } from "@/components/ui/EmptyState";

export default function PesquisaJuridicaPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Pesquisa jurídica</h1>
      <EmptyState
        title="Biblioteca de fontes ainda não está disponível"
        description="A busca de legislação, jurisprudência e doutrina (Módulo 3) ainda não foi implementada no backend."
      />
    </div>
  );
}
