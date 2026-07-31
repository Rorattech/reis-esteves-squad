"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ApiError, api } from "@/services/api";
import type { Case } from "@/types/api";

interface AdvanceStageActionProps {
  caseId: string;
  caseData: Case;
  /** true só quando o relato inicial já existe — o backend exige isso (422 sem ele). */
  hasIntake: boolean;
  canWrite: boolean;
  onAdvanced: () => void;
}

/**
 * Conclui a abertura do caso e o avança para Evidências (roadmap 2.6:
 * "o botão para Evidências só é liberado depois da transição aceita pelo
 * backend").
 *
 * Existe porque a triagem assistida por IA nem sempre produz uma recomendação
 * a revisar — sem provedor de IA configurado, `POST .../intake/run` responde
 * 503 e o caso nunca chega a `pending_approval`, deixando o fluxo de revisão
 * (IntakeReviewForm) sem nada para aprovar. Quando existe recomendação
 * pendente, este componente sai de cena: o caminho correto passa a ser
 * aprovar/corrigir/devolver a recomendação, não avançar por fora dela.
 *
 * A etapa só muda depois que o backend confirma — a interface nunca marca o
 * caso como avançado por conta própria (CLAUDE.md, seção 16).
 */
export function AdvanceStageAction({
  caseId,
  caseData,
  hasIntake,
  canWrite,
  onAdvanced,
}: AdvanceStageActionProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [advanceError, setAdvanceError] = useState<string | null>(null);

  const alreadyAdvanced = caseData.current_module !== "intake";
  const hasPendingRecommendation = caseData.status === "pending_approval";

  if (!canWrite || alreadyAdvanced || hasPendingRecommendation) return null;

  async function handleConfirm() {
    setConfirmOpen(false);
    setIsAdvancing(true);
    setAdvanceError(null);
    try {
      await api.advanceCaseStage(caseId, { notes: notes.trim() || null });
      setNotes("");
      onAdvanced();
    } catch (error) {
      setAdvanceError(
        error instanceof ApiError
          ? error.message
          : "Não foi possível avançar o caso para Evidências.",
      );
    } finally {
      setIsAdvancing(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
      <div>
        <h3 className="text-sm font-medium text-slate-900">Concluir a abertura do caso</h3>
        <p className="mt-1 text-sm text-slate-600">
          Libera a etapa de Evidências para envio de documentos. A decisão é sua e fica registrada
          no histórico do caso — nenhuma classificação da IA é dada como aprovada aqui.
        </p>
      </div>

      <div>
        <label htmlFor="advance-notes" className="block text-xs font-medium text-slate-700">
          Observação para o histórico <span className="font-normal text-slate-400">(opcional)</span>
        </label>
        <textarea
          id="advance-notes"
          rows={2}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Ex.: relato e documentos conferidos manualmente."
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
      </div>

      <button
        type="button"
        disabled={!hasIntake || isAdvancing}
        onClick={() => setConfirmOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isAdvancing ? "Avançando..." : "Avançar para Evidências"}
        <ArrowRight aria-hidden="true" className="h-4 w-4" />
      </button>

      {!hasIntake && (
        <p className="text-xs text-slate-500">
          Salve o relato inicial antes de avançar o caso para Evidências.
        </p>
      )}
      {advanceError && (
        <p role="alert" className="text-sm text-red-700">
          {advanceError}
        </p>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Avançar o caso para Evidências?"
        description="A etapa de Evidências fica liberada para envio de documentos. O caso continua podendo voltar para complementação, e nada é protocolado ou enviado para fora do sistema."
        confirmLabel="Avançar"
        cancelLabel="Cancelar"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
