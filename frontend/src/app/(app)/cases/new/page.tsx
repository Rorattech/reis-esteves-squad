"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FRAUD_TYPE_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { FraudType, UrgencyLevel } from "@/types/api";

/**
 * Espelha CaseCreate (backend/app/models/schemas/case.py) — só os campos
 * que este formulário preenche. client_id/area/matter existem no schema
 * real, mas não há endpoint de cliente nem tela de triagem ainda (ver
 * types/api.ts::CaseCreateInput).
 */
const caseCreateSchema = z.object({
  platform: z
    .string()
    .trim()
    .min(1, "Informe a plataforma envolvida.")
    .max(100, "Máximo de 100 caracteres."),
  fraud_type: z.enum(["pix", "marketplace", "fake_profile", "fake_lawyer", "other"], {
    message: "Selecione a modalidade do golpe.",
  }),
  urgency: z.enum(["low", "medium", "high", "critical"]).optional(),
});

type CaseCreateFormValues = z.infer<typeof caseCreateSchema>;

const FRAUD_TYPE_OPTIONS = Object.entries(FRAUD_TYPE_LABELS) as [FraudType, string][];
const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];

export default function NewCasePage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CaseCreateFormValues>({ resolver: zodResolver(caseCreateSchema) });

  async function onSubmit(values: CaseCreateFormValues) {
    setFormError(null);
    try {
      const created = await api.createCase(values);
      router.push(`/cases/${created.id}`);
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : "Não foi possível criar o caso. Tente novamente.",
      );
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <div>
        <Link href="/cases" className="text-sm text-slate-500 hover:text-slate-700">
          ← Voltar para Casos
        </Link>
        <h1 className="mt-2 text-lg font-semibold text-slate-900">Novo caso</h1>
        <p className="text-sm text-slate-500">
          Abra um caso de Direito Digital para este escritório. O relato inicial e o checklist de
          documentos são preenchidos na etapa de Intake, depois de criado.
        </p>
      </div>

      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
      >
        <div>
          <label htmlFor="platform" className="block text-sm font-medium text-slate-700">
            Plataforma envolvida
          </label>
          <input
            id="platform"
            type="text"
            placeholder="Ex.: WhatsApp, Shopee, Mercado Livre..."
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            {...register("platform")}
          />
          {errors.platform && (
            <p className="mt-1 text-xs text-red-600">{errors.platform.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="fraud_type" className="block text-sm font-medium text-slate-700">
            Modalidade do golpe
          </label>
          <select
            id="fraud_type"
            defaultValue=""
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            {...register("fraud_type")}
          >
            <option value="" disabled>
              Selecione...
            </option>
            {FRAUD_TYPE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {errors.fraud_type && (
            <p className="mt-1 text-xs text-red-600">{errors.fraud_type.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="urgency" className="block text-sm font-medium text-slate-700">
            Urgência
          </label>
          <select
            id="urgency"
            defaultValue="medium"
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

        {formError && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{formError}</p>
        )}

        <div className="flex justify-end gap-2">
          <Link
            href="/cases"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {isSubmitting ? "Criando..." : "Criar caso"}
          </button>
        </div>
      </form>
    </div>
  );
}
