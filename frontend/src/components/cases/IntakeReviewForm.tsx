"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FraudModalitySelect, PlatformSelect } from "@/components/cases/CatalogSelect";
import { useCatalog } from "@/hooks/useCatalog";
import { CASE_AREA_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { CaseArea, CaseStatus, FraudType, IntakeResult, UrgencyLevel } from "@/types/api";

const correctionSchema = z.object({
  notes: z.string().trim().min(1, "Justificativa obrigatória para corrigir ou devolver."),
  urgency: z.enum(["low", "medium", "high", "critical"]).optional(),
  area: z.enum(["civil", "family", "criminal", "labor", "consumer", "digital"]).optional(),
  matter: z.string().trim().max(255).optional(),
});
type CorrectionFormValues = z.infer<typeof correctionSchema>;

const returnSchema = z.object({
  notes: z.string().trim().min(1, "Justificativa obrigatória para corrigir ou devolver."),
});
type ReturnFormValues = z.infer<typeof returnSchema>;

const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];
const AREA_OPTIONS = Object.entries(CASE_AREA_LABELS) as [CaseArea, string][];

interface IntakeReviewFormProps {
  caseId: string;
  caseStatus: CaseStatus;
  result: IntakeResult | null;
  canWrite: boolean;
  onReviewed: () => void;
}

/**
 * Revisão humana (docs/roadmap_mvp_squad_digital.md, 2.6). Só aparece
 * quando `caseStatus === "pending_approval"` — o único estado em que o
 * backend aceita `POST .../intake/review` (fora dele, 409 — ver
 * IntakeReviewConflictError, backend/app/services/intake_orchestration_service.py).
 * A interface nunca chama "aprovado" antes da resposta do backend confirmar.
 */
export function IntakeReviewForm({
  caseId,
  caseStatus,
  result,
  canWrite,
  onReviewed,
}: IntakeReviewFormProps) {
  const { platforms, modalities, reload: reloadCatalog } = useCatalog();
  // A correção escolhe entradas do catálogo (não texto livre), então
  // plataforma e modalidade ficam em estado local, fora do schema do zod.
  // Começam vazias de propósito: a correção só envia o que o advogado mexeu.
  const [platformId, setPlatformId] = useState("");
  const [fraudModalityId, setFraudModalityId] = useState("");
  const [mode, setMode] = useState<"correct" | "return" | null>(null);
  const [approveConfirmOpen, setApproveConfirmOpen] = useState(false);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const correctionForm = useForm<CorrectionFormValues>({
    resolver: zodResolver(correctionSchema),
    values: {
      notes: "",
      urgency: result?.urgency,
      area: result?.area ?? undefined,
      matter: result?.matter ?? undefined,
    },
  });

  const returnForm = useForm<ReturnFormValues>({
    resolver: zodResolver(returnSchema),
    defaultValues: { notes: "" },
  });

  if (!canWrite) return null;

  if (caseStatus !== "pending_approval") {
    return (
      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        Não há nenhuma recomendação de triagem pendente de revisão no momento.
      </p>
    );
  }

  async function handleApprove() {
    setApproveConfirmOpen(false);
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      await api.reviewIntake(caseId, { decision: "approve" });
      onReviewed();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Não foi possível aprovar a triagem.");
    } finally {
      setIsSubmittingAction(false);
    }
  }

  async function handleCorrect(values: CorrectionFormValues) {
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      await api.reviewIntake(caseId, {
        decision: "correct",
        notes: values.notes,
        ...(platformId ? { platform_id: platformId } : {}),
        ...(fraudModalityId ? { fraud_modality_id: fraudModalityId } : {}),
        urgency: values.urgency,
        area: values.area,
        matter: values.matter,
      });
      setMode(null);
      onReviewed();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Não foi possível corrigir a triagem.");
    } finally {
      setIsSubmittingAction(false);
    }
  }

  async function handleReturn(values: ReturnFormValues) {
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      await api.reviewIntake(caseId, { decision: "return_for_information", notes: values.notes });
      setMode(null);
      onReviewed();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível devolver o caso para complementação.",
      );
    } finally {
      setIsSubmittingAction(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
      <p className="text-sm text-slate-600">
        A classificação acima é uma recomendação assistida por IA — nenhuma decisão jurídica é
        definitiva até esta revisão.
      </p>

      {mode === null && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setApproveConfirmOpen(true)}
            disabled={isSubmittingAction}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            Aprovar
          </button>
          <button
            type="button"
            onClick={() => setMode("correct")}
            disabled={isSubmittingAction}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Corrigir
          </button>
          <button
            type="button"
            onClick={() => setMode("return")}
            disabled={isSubmittingAction}
            className="rounded-md border border-amber-300 px-3 py-1.5 text-sm font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60"
          >
            Devolver para complementação
          </button>
        </div>
      )}

      {mode === "correct" && (
        <form onSubmit={correctionForm.handleSubmit(handleCorrect)} noValidate className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <PlatformSelect
              platforms={platforms}
              value={platformId}
              onChange={setPlatformId}
              onCreated={reloadCatalog}
            />

            <FraudModalitySelect
              modalities={modalities}
              value={fraudModalityId}
              onChange={setFraudModalityId}
              onCreated={reloadCatalog}
            />

            <div>
              <label htmlFor="review-urgency" className="block text-xs font-medium text-slate-700">
                Urgência
              </label>
              <select
                id="review-urgency"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
                {...correctionForm.register("urgency")}
              >
                {URGENCY_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="review-area" className="block text-xs font-medium text-slate-700">
                Área
              </label>
              <select
                id="review-area"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
                {...correctionForm.register("area")}
              >
                <option value="">—</option>
                {AREA_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="review-matter" className="block text-xs font-medium text-slate-700">
                Matéria
              </label>
              <input
                id="review-matter"
                type="text"
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
                {...correctionForm.register("matter")}
              />
            </div>
          </div>

          <div>
            <label htmlFor="review-correct-notes" className="block text-xs font-medium text-slate-700">
              Justificativa da correção
            </label>
            <textarea
              id="review-correct-notes"
              rows={3}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...correctionForm.register("notes")}
            />
            {correctionForm.formState.errors.notes && (
              <p className="mt-1 text-xs text-red-600">
                {correctionForm.formState.errors.notes.message}
              </p>
            )}
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setMode(null)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmittingAction}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {isSubmittingAction ? "Enviando..." : "Confirmar correção"}
            </button>
          </div>
        </form>
      )}

      {mode === "return" && (
        <form onSubmit={returnForm.handleSubmit(handleReturn)} noValidate className="space-y-3">
          <div>
            <label htmlFor="review-return-notes" className="block text-xs font-medium text-slate-700">
              O que falta para complementar o caso?
            </label>
            <textarea
              id="review-return-notes"
              rows={3}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...returnForm.register("notes")}
            />
            {returnForm.formState.errors.notes && (
              <p className="mt-1 text-xs text-red-600">{returnForm.formState.errors.notes.message}</p>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setMode(null)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmittingAction}
              className="rounded-md bg-amber-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-60"
            >
              {isSubmittingAction ? "Enviando..." : "Confirmar devolução"}
            </button>
          </div>
        </form>
      )}

      {actionError && <p className="text-sm text-red-700">{actionError}</p>}

      <ConfirmDialog
        open={approveConfirmOpen}
        title="Aprovar a recomendação da triagem?"
        description="O caso avança para o módulo de Evidências. Esta ação fica registrada no histórico do caso."
        confirmLabel="Aprovar"
        cancelLabel="Cancelar"
        onConfirm={handleApprove}
        onCancel={() => setApproveConfirmOpen(false)}
      />
    </div>
  );
}
