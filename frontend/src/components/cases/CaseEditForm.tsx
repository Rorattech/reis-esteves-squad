"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { FraudModalitySelect, PlatformSelect } from "@/components/cases/CatalogSelect";
import { ClientPicker, type ClientSelection } from "@/components/clients/ClientPicker";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useCatalog } from "@/hooks/useCatalog";
import { CASE_AREA_LABELS, URGENCY_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { Case, CaseArea, UrgencyLevel } from "@/types/api";

const URGENCY_OPTIONS = Object.entries(URGENCY_LABELS) as [UrgencyLevel, string][];
const AREA_OPTIONS = Object.entries(CASE_AREA_LABELS) as [CaseArea, string][];

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none";
const selectClass = `${inputClass} bg-white`;

interface CaseEditFormProps {
  /** Só é montado com o caso já carregado — ver page.tsx. */
  caseData: Case;
}

/**
 * Formulário de edição do cadastro do caso.
 *
 * O código do caso não aparece aqui: é emitido uma vez e não é editável — é o
 * que permite citá-lo com segurança fora do sistema. Cadastrar um cliente novo
 * também não é possível daqui; a edição só re-vincula um cliente existente
 * (cadastro novo é na abertura do caso ou em /clients/new), para que uma
 * correção de caso não crie um cliente sem querer.
 */
export function CaseEditForm({ caseData }: CaseEditFormProps) {
  const router = useRouter();
  const { platforms, modalities, isLoading, error, reload } = useCatalog();

  const [platformId, setPlatformId] = useState(caseData.platform_entry.id);
  const [fraudModalityId, setFraudModalityId] = useState(caseData.fraud_modality.id);
  const [urgency, setUrgency] = useState<UrgencyLevel>(caseData.urgency);
  const [area, setArea] = useState<CaseArea | "">(caseData.area ?? "");
  const [matter, setMatter] = useState(caseData.matter ?? "");
  const [clientSelection, setClientSelection] = useState<ClientSelection>(
    // ClientSummary basta para o picker (ver PickedClient) — o documento não
    // vem numa listagem de casos, e não é necessário aqui.
    caseData.client ? { kind: "existing", client: caseData.client } : { kind: "none" },
  );

  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setIsSubmitting(true);
    try {
      // client_id null desvincula o cliente; area em branco é omitida — o
      // backend não aceita "" no enum.
      await api.updateCase(caseData.id, {
        platform_id: platformId,
        fraud_modality_id: fraudModalityId,
        urgency,
        client_id: clientSelection.kind === "existing" ? clientSelection.client.id : null,
        ...(area ? { area } : {}),
        matter: matter.trim(),
      });
      router.push(`/cases/${caseData.id}`);
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Não foi possível salvar o caso. Tente novamente.",
      );
      setIsSubmitting(false);
    }
  }

  if (isLoading) return <LoadingState label="Carregando catálogo de classificação..." />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-6 rounded-lg border border-slate-200 bg-white p-5"
    >
      <PlatformSelect
        platforms={platforms}
        value={platformId}
        onChange={setPlatformId}
        onCreated={reload}
      />

      <FraudModalitySelect
        modalities={modalities}
        value={fraudModalityId}
        onChange={setFraudModalityId}
        onCreated={reload}
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
        <span className="block text-sm font-medium text-slate-700">
          Cliente <span className="font-normal text-slate-400">(opcional)</span>
        </span>
        <div className="mt-1">
          <ClientPicker
            selection={clientSelection}
            onSelect={setClientSelection}
            onRequestNewClient={() => router.push("/clients/new")}
          />
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Remover o cliente aqui apenas o desvincula deste caso — o cadastro dele permanece.
        </p>
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
          className={inputClass}
        />
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
