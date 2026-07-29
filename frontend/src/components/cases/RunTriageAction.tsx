"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ApiError, api } from "@/services/api";

interface RunTriageActionProps {
  caseId: string;
  /** true só quando o relato inicial já existe — POST .../intake/run exige isso (422 sem ele). */
  hasIntake: boolean;
  canWrite: boolean;
  onCompleted: () => void;
}

/**
 * Ação "Executar Triagem" (docs/roadmap_mvp_squad_digital.md, 2.6):
 * confirmação antes de rodar, estado de processamento, bloqueio de clique
 * duplicado, e atualização do resultado só depois da resposta do backend
 * (nunca otimista — a classificação vem inteira do backend).
 */
export function RunTriageAction({ caseId, hasIntake, canWrite, onCompleted }: RunTriageActionProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function handleConfirm() {
    setConfirmOpen(false);
    setIsRunning(true);
    setRunError(null);
    try {
      await api.runIntake(caseId);
      onCompleted();
    } catch (error) {
      setRunError(
        error instanceof ApiError
          ? error.message
          : "Não foi possível executar a triagem. Tente novamente.",
      );
    } finally {
      setIsRunning(false);
    }
  }

  if (!canWrite) return null;

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        disabled={!hasIntake || isRunning}
        onClick={() => setConfirmOpen(true)}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isRunning ? "Executando triagem..." : "Executar triagem"}
      </button>
      {!hasIntake && (
        <p className="text-xs text-slate-500">Salve o relato inicial antes de executar a triagem.</p>
      )}
      {runError && <p className="text-sm text-red-700">{runError}</p>}

      <ConfirmDialog
        open={confirmOpen}
        title="Executar triagem automática?"
        description="O relato registrado vai ser analisado para classificar plataforma, modalidade, urgência e montar o checklist de documentos. O resultado é sempre uma recomendação — vai depender da sua revisão antes de avançar o caso."
        confirmLabel="Executar"
        cancelLabel="Cancelar"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
