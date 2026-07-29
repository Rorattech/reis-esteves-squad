import { EmptyState } from "@/components/ui/EmptyState";

/**
 * Estado honesto para abas do caso cujo módulo (Intake, Evidências, Pesquisa,
 * Estratégia, Minuta, Revisão, Histórico) ainda não existe no backend — CLAUDE.md
 * proíbe fabricar dado, então isso é uma vitrine vazia, não uma tela fake.
 */
export function ModulePlaceholder({ moduleName }: { moduleName: string }) {
  return (
    <EmptyState
      title={`${moduleName} ainda não está disponível`}
      description="Este módulo do Squad Digital ainda não foi implementado no backend. Volte aqui quando o time avançar para essa etapa do workflow."
    />
  );
}
