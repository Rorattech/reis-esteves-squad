"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { FraudModalitySelect, PlatformSelect } from "@/components/cases/CatalogSelect";
import { ClientForm } from "@/components/clients/ClientForm";
import { ClientPicker, type ClientSelection } from "@/components/clients/ClientPicker";
import { toClientPayload, type ClientFormValues } from "@/components/clients/clientSchema";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useCatalog } from "@/hooks/useCatalog";
import { CASE_AREA_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { CaseArea, CaseCreateInput, UrgencyLevel } from "@/types/api";

const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];
const AREA_OPTIONS = Object.entries(CASE_AREA_LABELS) as [CaseArea, string][];

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none";
const selectClass = `${inputClass} bg-white`;

export default function NewCasePage() {
  const router = useRouter();
  const { platforms, modalities, isLoading, error, reload } = useCatalog();

  const [platformId, setPlatformId] = useState("");
  const [fraudModalityId, setFraudModalityId] = useState("");
  const [urgency, setUrgency] = useState<UrgencyLevel>("medium");
  const [area, setArea] = useState<CaseArea | "">("");
  const [matter, setMatter] = useState("");
  const [clientSelection, setClientSelection] = useState<ClientSelection>({ kind: "none" });
  const [isRegisteringClient, setIsRegisteringClient] = useState(false);

  const [fieldErrors, setFieldErrors] = useState<{ platform?: string; modality?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);

    const errors: { platform?: string; modality?: string } = {};
    if (!platformId) errors.platform = "Selecione a plataforma envolvida.";
    if (!fraudModalityId) errors.modality = "Selecione a modalidade do golpe.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const payload: CaseCreateInput = {
      platform_id: platformId,
      fraud_modality_id: fraudModalityId,
      urgency,
      ...(area ? { area } : {}),
      ...(matter.trim() ? { matter: matter.trim() } : {}),
    };

    // client_id e client são mutuamente exclusivos no backend — o cliente novo
    // é criado na mesma transação do caso, então uma falha aqui não deixa
    // cadastro órfão.
    if (clientSelection.kind === "existing") {
      payload.client_id = clientSelection.client.id;
    } else if (clientSelection.kind === "new") {
      payload.client = toClientPayload(clientSelection.values);
    }

    setIsSubmitting(true);
    try {
      const created = await api.createCase(payload);
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Não foi possível criar o caso. Tente novamente.",
      );
      setIsSubmitting(false);
    }
  }

  function handleNewClientSubmit(values: ClientFormValues) {
    setClientSelection({ kind: "new", values });
    setIsRegisteringClient(false);
    return Promise.resolve();
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
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

      {isLoading && <LoadingState label="Carregando catálogo de classificação..." />}

      {!isLoading && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !error && (
        <form
          onSubmit={handleSubmit}
          noValidate
          className="space-y-6 rounded-lg border border-slate-200 bg-white p-5"
        >
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-slate-900">Cliente</legend>

            {isRegisteringClient ? (
              <div className="rounded-md border border-slate-200 p-4">
                <ClientForm
                  onSubmit={handleNewClientSubmit}
                  onCancel={() => setIsRegisteringClient(false)}
                  submitLabel="Usar este cliente"
                />
              </div>
            ) : (
              <ClientPicker
                selection={clientSelection}
                onSelect={setClientSelection}
                onRequestNewClient={() => setIsRegisteringClient(true)}
              />
            )}

            <p className="text-xs text-slate-500">
              O cliente pode ficar em branco e ser vinculado depois, na edição do caso.
            </p>
          </fieldset>

          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-slate-900">Classificação</legend>

            <PlatformSelect
              platforms={platforms}
              value={platformId}
              onChange={setPlatformId}
              onCreated={reload}
              error={fieldErrors.platform}
            />

            <FraudModalitySelect
              modalities={modalities}
              value={fraudModalityId}
              onChange={setFraudModalityId}
              onCreated={reload}
              error={fieldErrors.modality}
            />

            <div>
              <label htmlFor="urgency" className="block text-sm font-medium text-slate-700">
                Urgência
              </label>
              <select
                id="urgency"
                value={urgency}
                onChange={(event) => setUrgency(event.target.value as UrgencyLevel)}
                className={selectClass}
              >
                {URGENCY_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="area" className="block text-sm font-medium text-slate-700">
                Área <span className="font-normal text-slate-400">(opcional)</span>
              </label>
              <select
                id="area"
                value={area}
                onChange={(event) => setArea(event.target.value as CaseArea | "")}
                className={selectClass}
              >
                <option value="">A definir na triagem</option>
                {AREA_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="matter" className="block text-sm font-medium text-slate-700">
                Matéria <span className="font-normal text-slate-400">(opcional)</span>
              </label>
              <input
                id="matter"
                type="text"
                value={matter}
                onChange={(event) => setMatter(event.target.value)}
                placeholder="Ex.: golpe do PIX via WhatsApp clonado"
                className={inputClass}
              />
            </div>
          </fieldset>

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
              disabled={isSubmitting || isRegisteringClient}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {isSubmitting ? "Criando..." : "Criar caso"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
