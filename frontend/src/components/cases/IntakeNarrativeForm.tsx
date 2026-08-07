"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FraudModalitySelect, PlatformSelect } from "@/components/cases/CatalogSelect";
import { useCatalog } from "@/hooks/useCatalog";
import { URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { Case, CaseIntake, UrgencyLevel } from "@/types/api";

/**
 * Espelha CaseUpdate (platform/fraud_type/urgency, backend/app/models/schemas/case.py)
 * + CaseIntakeCreate (o resto, backend/app/models/schemas/case_intake.py).
 * claimed_documents/pending_information são textareas de uma linha por
 * item — list[str] no schema real, sem campo de lista dinâmica dedicado.
 */
const narrativeFormSchema = z.object({
  urgency: z.enum(["low", "medium", "high", "critical"], {
    message: "Selecione a urgência relatada.",
  }),
  narrative: z.string().trim().min(1, "Descreva o relato do cliente."),
  estimated_loss_amount: z.string().trim().optional(),
  incident_date: z.string().trim().optional(),
  has_police_report: z.enum(["yes", "no", "unknown"]),
  claimed_documents: z.string().trim().optional(),
  pending_information: z.string().trim().optional(),
});

type NarrativeFormValues = z.infer<typeof narrativeFormSchema>;

const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];

function linesToList(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function listToLines(value: string[]): string {
  return value.join("\n");
}

interface IntakeNarrativeFormProps {
  caseData: Case;
  intake: CaseIntake | null;
  canWrite: boolean;
  onSaved: () => void;
}

/**
 * Formulário de relato inicial (docs/roadmap_mvp_squad_digital.md, 2.6).
 * Salva em dois passos reais — nenhum campo é inventado:
 * `PATCH /cases/{id}` (plataforma/modalidade/urgência, já existentes desde
 * a abertura do caso) e `POST /cases/{id}/intake` (o resto, específico do
 * relato — idempotente, sempre substitui o relato anterior).
 */
export function IntakeNarrativeForm({ caseData, intake, canWrite, onSaved }: IntakeNarrativeFormProps) {
  const [formError, setFormError] = useState<string | null>(null);
  const { platforms, modalities, reload: reloadCatalog } = useCatalog();

  // Classificação vem do catálogo do escritório, então mora em estado local e
  // não no schema do formulário — o zod aqui cobre só os campos do relato.
  const [platformId, setPlatformId] = useState(caseData.platform_entry.id);
  const [fraudModalityId, setFraudModalityId] = useState(caseData.fraud_modality.id);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<NarrativeFormValues>({
    resolver: zodResolver(narrativeFormSchema),
    values: {
      urgency: caseData.urgency,
      narrative: intake?.narrative ?? "",
      estimated_loss_amount: intake?.estimated_loss_amount ?? "",
      incident_date: intake?.incident_date ?? "",
      has_police_report:
        intake?.has_police_report === true ? "yes" : intake?.has_police_report === false ? "no" : "unknown",
      claimed_documents: listToLines(intake?.claimed_documents ?? []),
      pending_information: listToLines(intake?.pending_information ?? []),
    },
  });

  async function onSubmit(values: NarrativeFormValues) {
    setFormError(null);
    try {
      await api.updateCase(caseData.id, {
        platform_id: platformId,
        fraud_modality_id: fraudModalityId,
        urgency: values.urgency,
      });
      await api.submitCaseIntake(caseData.id, {
        narrative: values.narrative,
        estimated_loss_amount:
          values.estimated_loss_amount && values.estimated_loss_amount.length > 0
            ? Number(values.estimated_loss_amount)
            : null,
        incident_date: values.incident_date && values.incident_date.length > 0 ? values.incident_date : null,
        has_police_report: values.has_police_report === "unknown" ? null : values.has_police_report === "yes",
        claimed_documents: linesToList(values.claimed_documents),
        pending_information: linesToList(values.pending_information),
      });
      onSaved();
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : "Não foi possível salvar o relato inicial.",
      );
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
    >
      <fieldset disabled={!canWrite || isSubmitting} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
            <label htmlFor="urgency" className="block text-sm font-medium text-slate-700">
              Urgência relatada
            </label>
            <select
              id="urgency"
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...register("urgency")}
            >
              {URGENCY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            {errors.urgency && <p className="mt-1 text-xs text-red-600">{errors.urgency.message}</p>}
          </div>
        </div>

        <div>
          <label htmlFor="narrative" className="block text-sm font-medium text-slate-700">
            Relato do cliente
          </label>
          <textarea
            id="narrative"
            rows={5}
            placeholder="Descreva, com as palavras do cliente, o que aconteceu..."
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            {...register("narrative")}
          />
          {errors.narrative && <p className="mt-1 text-xs text-red-600">{errors.narrative.message}</p>}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="estimated_loss_amount" className="block text-sm font-medium text-slate-700">
              Valor envolvido (R$)
            </label>
            <input
              id="estimated_loss_amount"
              type="number"
              min={0}
              step="0.01"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...register("estimated_loss_amount")}
            />
            {errors.estimated_loss_amount && (
              <p className="mt-1 text-xs text-red-600">{errors.estimated_loss_amount.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="incident_date" className="block text-sm font-medium text-slate-700">
              Data do ocorrido
            </label>
            <input
              id="incident_date"
              type="date"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...register("incident_date")}
            />
          </div>

          <div>
            <span className="block text-sm font-medium text-slate-700">Existe Boletim de Ocorrência?</span>
            <div className="mt-2 flex gap-4 text-sm text-slate-700">
              <label className="flex items-center gap-1.5">
                <input type="radio" value="yes" {...register("has_police_report")} />
                Sim
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" value="no" {...register("has_police_report")} />
                Não
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" value="unknown" {...register("has_police_report")} />
                Não sei
              </label>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="claimed_documents" className="block text-sm font-medium text-slate-700">
              Documentos já disponíveis
            </label>
            <textarea
              id="claimed_documents"
              rows={3}
              placeholder={"Um documento por linha, ex.:\ncomprovante_pix.png\nprint_conversa.png"}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...register("claimed_documents")}
            />
          </div>

          <div>
            <label htmlFor="pending_information" className="block text-sm font-medium text-slate-700">
              Informações ainda desconhecidas
            </label>
            <textarea
              id="pending_information"
              rows={3}
              placeholder={"Uma informação por linha, ex.:\nvalor exato transferido\ndata exata do golpe"}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              {...register("pending_information")}
            />
          </div>
        </div>

        {formError && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{formError}</p>
        )}

        {canWrite && (
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {isSubmitting ? "Salvando..." : intake ? "Salvar alterações" : "Salvar relato inicial"}
            </button>
          </div>
        )}
      </fieldset>
    </form>
  );
}
