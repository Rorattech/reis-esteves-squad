"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CASE_AREA_LABELS, FRAUD_TYPE_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { Case, CaseArea, FraudType, UrgencyLevel } from "@/types/api";

/** Espelha CaseUpdate (backend/app/models/schemas/case.py) — só os campos de cadastro. */
const caseEditSchema = z.object({
  platform: z
    .string()
    .trim()
    .min(1, "Informe a plataforma envolvida.")
    .max(100, "Máximo de 100 caracteres."),
  fraud_type: z.enum(["pix", "marketplace", "fake_profile", "fake_lawyer", "other"]),
  urgency: z.enum(["low", "medium", "high", "critical"]),
  client_id: z
    .string()
    .trim()
    .uuid("Token do cliente inválido — use o identificador completo do cliente.")
    .optional()
    .or(z.literal("")),
  area: z
    .enum(["civil", "family", "criminal", "labor", "consumer", "digital"])
    .optional()
    .or(z.literal("")),
  matter: z.string().trim().max(255, "Máximo de 255 caracteres.").optional(),
});

type CaseEditFormValues = z.infer<typeof caseEditSchema>;

const FRAUD_TYPE_OPTIONS = Object.entries(FRAUD_TYPE_LABELS) as [FraudType, string][];
const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];
const AREA_OPTIONS = Object.entries(CASE_AREA_LABELS) as [CaseArea, string][];

interface CaseEditFormProps {
  /** Só é montado com o caso já carregado — ver page.tsx. */
  caseData: Case;
}

/**
 * Formulário de edição do cadastro do caso.
 *
 * Recebe o caso já carregado e o usa como `defaultValues` — a página só monta
 * este componente depois do fetch. Semear o formulário com a opção `values`
 * do react-hook-form seria pior: ela é uma fonte controlada e re-sincroniza o
 * campo por cima do que o usuário digitou, desfazendo edições.
 */
export function CaseEditForm({ caseData }: CaseEditFormProps) {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CaseEditFormValues>({
    resolver: zodResolver(caseEditSchema),
    defaultValues: {
      platform: caseData.platform,
      fraud_type: caseData.fraud_type,
      urgency: caseData.urgency,
      client_id: caseData.client_id ?? "",
      area: caseData.area ?? "",
      matter: caseData.matter ?? "",
    },
  });

  async function onSubmit(values: CaseEditFormValues) {
    setFormError(null);
    try {
      // client_id em branco vira null (desvincula o cliente); area em branco é
      // omitida — o backend não aceita "" em nenhum dos dois.
      await api.updateCase(caseData.id, {
        platform: values.platform,
        fraud_type: values.fraud_type,
        urgency: values.urgency,
        client_id: values.client_id ? values.client_id : null,
        ...(values.area ? { area: values.area } : {}),
        matter: values.matter ?? "",
      });
      router.push(`/cases/${caseData.id}`);
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Não foi possível salvar o caso. Tente novamente.",
      );
    }
  }

  return (
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
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          {...register("platform")}
        />
        {errors.platform && <p className="mt-1 text-xs text-red-600">{errors.platform.message}</p>}
      </div>

      <div>
        <label htmlFor="fraud_type" className="block text-sm font-medium text-slate-700">
          Modalidade do golpe
        </label>
        <select
          id="fraud_type"
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          {...register("fraud_type")}
        >
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
          Deixe em branco para desvincular o cliente deste caso.
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
          href={`/cases/${caseData.id}`}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancelar
        </Link>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          {isSubmitting ? "Salvando..." : "Salvar alterações"}
        </button>
      </div>
    </form>
  );
}
