"use client";

import { useId, useState } from "react";

import { FRAUD_TYPE_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { FraudModality, FraudType, Platform } from "@/types/api";

/** Valor sentinela do <option> que abre o cadastro de uma entrada nova. */
const CREATE_OPTION = "__create__";

const FRAUD_FAMILY_OPTIONS = Object.entries(FRAUD_TYPE_LABELS) as [FraudType, string][];

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none";
const selectClass = `${inputClass} bg-white`;

interface PlatformSelectProps {
  platforms: Platform[];
  value: string;
  onChange: (platformId: string) => void;
  /** Chamado depois de cadastrar uma entrada, para recarregar o catálogo. */
  onCreated: () => void;
  error?: string;
}

/**
 * Seleção da plataforma envolvida a partir do catálogo do escritório, com a
 * opção "Outro" que cadastra uma entrada reutilizável.
 *
 * A plataforma era texto livre até a Fase 2.7 — o que fazia "WhatsApp",
 * "whatsapp" e "Whats" virarem três plataformas diferentes no mesmo escritório.
 */
export function PlatformSelect({
  platforms,
  value,
  onChange,
  onCreated,
  error,
}: PlatformSelectProps) {
  // useId, e não um id fixo: a mesma página pode montar dois seletores de
  // plataforma (relato inicial + correção da triagem), e ids duplicados
  // quebram a associação <label for> para leitor de tela e teclado.
  const selectId = useId();
  const newLabelId = useId();
  const [isCreating, setIsCreating] = useState(false);
  const [label, setLabel] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function handleCreate() {
    if (!label.trim()) {
      setCreateError("Informe o nome da plataforma.");
      return;
    }
    setIsSaving(true);
    setCreateError(null);
    try {
      const created = await api.createPlatform({ label: label.trim() });
      onChange(created.id);
      onCreated();
      setIsCreating(false);
      setLabel("");
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : "Não foi possível cadastrar a plataforma.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div>
      <label htmlFor={selectId} className="block text-sm font-medium text-slate-700">
        Plataforma envolvida
      </label>
      <select
        id={selectId}
        value={isCreating ? CREATE_OPTION : value}
        onChange={(event) => {
          if (event.target.value === CREATE_OPTION) {
            setIsCreating(true);
            return;
          }
          setIsCreating(false);
          onChange(event.target.value);
        }}
        className={selectClass}
      >
        <option value="" disabled>
          Selecione...
        </option>
        {platforms.map((platform) => (
          <option key={platform.id} value={platform.id}>
            {platform.label}
          </option>
        ))}
        <option value={CREATE_OPTION}>Outro (cadastrar)</option>
      </select>

      {isCreating && (
        <div className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <label htmlFor={newLabelId} className="block text-xs font-medium text-slate-700">
            Nome da plataforma
          </label>
          <input
            id={newLabelId}
            type="text"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Ex.: Kwai"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
          <p className="text-xs text-slate-500">
            Fica salva no catálogo do escritório e pode ser reutilizada em outros casos.
          </p>
          {createError && (
            <p role="alert" className="text-xs text-red-600">
              {createError}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCreate}
              disabled={isSaving}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {isSaving ? "Salvando..." : "Salvar plataforma"}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsCreating(false);
                setCreateError(null);
              }}
              className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

interface FraudModalitySelectProps {
  modalities: FraudModality[];
  value: string;
  onChange: (modalityId: string) => void;
  onCreated: () => void;
  error?: string;
}

/**
 * Seleção da modalidade do golpe, com cadastro de modalidades próprias.
 *
 * Cadastrar exige escolher uma **família**: é ela que o grafo e os prompts
 * leem (ver backend/app/models/catalog.py). Sem família, a modalidade nova
 * seria texto que os agentes não sabem interpretar.
 */
export function FraudModalitySelect({
  modalities,
  value,
  onChange,
  onCreated,
  error,
}: FraudModalitySelectProps) {
  const selectId = useId();
  const newLabelId = useId();
  const familyId = useId();
  const [isCreating, setIsCreating] = useState(false);
  const [label, setLabel] = useState("");
  const [family, setFamily] = useState<FraudType>("other");
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function handleCreate() {
    if (!label.trim()) {
      setCreateError("Descreva a modalidade do golpe.");
      return;
    }
    setIsSaving(true);
    setCreateError(null);
    try {
      const created = await api.createFraudModality({ label: label.trim(), family });
      onChange(created.id);
      onCreated();
      setIsCreating(false);
      setLabel("");
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : "Não foi possível cadastrar a modalidade.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div>
      <label htmlFor={selectId} className="block text-sm font-medium text-slate-700">
        Modalidade do golpe
      </label>
      <select
        id={selectId}
        value={isCreating ? CREATE_OPTION : value}
        onChange={(event) => {
          if (event.target.value === CREATE_OPTION) {
            setIsCreating(true);
            return;
          }
          setIsCreating(false);
          onChange(event.target.value);
        }}
        className={selectClass}
      >
        <option value="" disabled>
          Selecione...
        </option>
        {modalities.map((modality) => (
          <option key={modality.id} value={modality.id}>
            {modality.label}
          </option>
        ))}
        <option value={CREATE_OPTION}>Outro (cadastrar)</option>
      </select>

      {isCreating && (
        <div className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <label htmlFor={newLabelId} className="block text-xs font-medium text-slate-700">
            Descreva o golpe
          </label>
          <input
            id={newLabelId}
            type="text"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Ex.: Golpe da falsa central de atendimento"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />

          <label htmlFor={familyId} className="block text-xs font-medium text-slate-700">
            Família
          </label>
          <select
            id={familyId}
            value={family}
            onChange={(event) => setFamily(event.target.value as FraudType)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          >
            {FRAUD_FAMILY_OPTIONS.map(([value, familyLabel]) => (
              <option key={value} value={value}>
                {familyLabel}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">
            A família orienta a análise dos agentes. A modalidade fica salva no catálogo do
            escritório.
          </p>

          {createError && (
            <p role="alert" className="text-xs text-red-600">
              {createError}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCreate}
              disabled={isSaving}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {isSaving ? "Salvando..." : "Salvar modalidade"}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsCreating(false);
                setCreateError(null);
              }}
              className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
