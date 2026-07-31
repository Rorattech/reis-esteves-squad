"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CASE_AREA_LABELS, FRAUD_TYPE_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { CaseArea, FraudType, UrgencyLevel } from "@/types/api";

/** Espelha CaseCreate (backend/app/models/schemas/case.py). */
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
  // client_id/area/matter são opcionais no backend: podem não ser conhecidos
  // na abertura e serem preenchidos depois, pela triagem ou pela tela de
  // edição do caso. O formato do token é validado aqui; a existência do
  // cliente neste tenant, só o backend pode confirmar (404 "Cliente não
  // encontrado.").
  client_id: z
    .string()
    .trim()
    .uuid("Token do cliente inválido — use o identificador completo do cliente.")
    .optional()
    .or(z.literal("")),
  area: z.enum(["civil", "family", "criminal", "labor", "consumer", "digital"]).optional().or(z.literal("")),
  matter: z.string().trim().max(255, "Máximo de 255 caracteres.").optional(),
});

type CaseCreateFormValues = z.infer<typeof caseCreateSchema>;

const FRAUD_TYPE_OPTIONS = Object.entries(FRAUD_TYPE_LABELS) as [FraudType, string][];
const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];
const AREA_OPTIONS = Object.entries(CASE_AREA_LABELS) as [CaseArea, string][];

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
      // Campos opcionais em branco são omitidos do payload: enviar "" faria o
      // backend rejeitar com 422 (client_id espera UUID, area espera um valor
      // do enum CaseArea).
      const created = await api.createCase({
        platform: values.platform,
        fraud_type: values.fraud_type,
        urgency: values.urgency,
        ...(values.client_id ? { client_id: values.client_id } : {}),
        ...(values.area ? { area: values.area } : {}),
        ...(values.matter ? { matter: values.matter } : {}),
      });
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
          documentos são preenchidos na etapa de Abertura de caso, depois de criado.
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

        <div>
          <label htmlFor="client_id" className="block text-sm font-medium text-slate-700">
            Token do cliente <span className="font-normal text-slate-400">(opcional)</span>
          </label>
          <input
            id="client_id"
            type="text"
            placeholder="Ex.: 3f2a9c10-4b7e-4d51-9a2f-8e0c1d6b5a44"
            aria-describedby="client_id-help"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm focus:border-slate-500 focus:outline-none"
            {...register("client_id")}
          />
          <p id="client_id-help" className="mt-1 text-xs text-slate-500">
            Identificador do cliente já cadastrado neste escritório. Pode ficar em branco e ser
            preenchido depois, na edição do caso.
          </p>
          {errors.client_id && (
            <p className="mt-1 text-xs text-red-600">{errors.client_id.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="area" className="block text-sm font-medium text-slate-700">
            Área <span className="font-normal text-slate-400">(opcional)</span>
          </label>
          <select
            id="area"
            defaultValue=""
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            {...register("area")}
          >
            <option value="">A definir na triagem</option>
            {AREA_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {errors.area && <p className="mt-1 text-xs text-red-600">{errors.area.message}</p>}
        </div>

        <div>
          <label htmlFor="matter" className="block text-sm font-medium text-slate-700">
            Matéria <span className="font-normal text-slate-400">(opcional)</span>
          </label>
          <input
            id="matter"
            type="text"
            placeholder="Ex.: golpe do PIX via WhatsApp clonado"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            {...register("matter")}
          />
          {errors.matter && <p className="mt-1 text-xs text-red-600">{errors.matter.message}</p>}
        </div>

        {formError && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {formError}
          </p>
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
