"use client";

import { useState } from "react";

import { useClients } from "@/hooks/useClients";
import { formatDocument } from "@/lib/documents";

import type { ClientFormValues } from "./clientSchema";

/**
 * O mínimo que o picker precisa para exibir um cliente já escolhido.
 *
 * Mais frouxo que `Client` de propósito: quando o cliente vem de dentro de um
 * caso ele chega como `ClientSummary`, que não carrega documento — listagens
 * de caso não expõem CPF (ver ClientSummary no backend).
 */
export interface PickedClient {
  id: string;
  code: string;
  full_name: string;
  document_number?: string | null;
}

/**
 * Como o cliente foi informado na abertura do caso. As duas formas são
 * mutuamente exclusivas no backend (ver CaseCreate).
 */
export type ClientSelection =
  | { kind: "none" }
  | { kind: "existing"; client: PickedClient }
  | { kind: "new"; values: ClientFormValues };

interface ClientPickerProps {
  selection: ClientSelection;
  onSelect: (selection: ClientSelection) => void;
  /** Abre o formulário de cadastro inline (a página é quem o renderiza). */
  onRequestNewClient: () => void;
}

/**
 * Escolha do cliente do caso: busca por nome, CPF/CNPJ ou código.
 *
 * Substitui o antigo campo "Token do cliente", que pedia ao advogado que
 * colasse um UUID à mão — sem nenhuma tela no produto que permitisse
 * descobri-lo.
 */
export function ClientPicker({ selection, onSelect, onRequestNewClient }: ClientPickerProps) {
  const [search, setSearch] = useState("");
  const { clients, isLoading, error } = useClients(search);

  if (selection.kind === "existing") {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
        <p className="text-sm font-medium text-slate-900">{selection.client.full_name}</p>
        <p className="text-xs text-slate-500">
          {selection.client.code}
          {selection.client.document_number
            ? ` · ${formatDocument(selection.client.document_number)}`
            : ""}
        </p>
        <button
          type="button"
          onClick={() => onSelect({ kind: "none" })}
          className="mt-2 text-xs font-medium text-slate-600 underline hover:text-slate-900"
        >
          Trocar cliente
        </button>
      </div>
    );
  }

  if (selection.kind === "new") {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
        <p className="text-sm font-medium text-slate-900">{selection.values.full_name}</p>
        <p className="text-xs text-slate-500">
          Novo cliente — será cadastrado junto com o caso
        </p>
        <button
          type="button"
          onClick={() => onSelect({ kind: "none" })}
          className="mt-2 text-xs font-medium text-slate-600 underline hover:text-slate-900"
        >
          Trocar cliente
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        type="search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Buscar por nome, CPF/CNPJ ou código..."
        aria-label="Buscar cliente"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
      />

      <div className="max-h-48 overflow-y-auto rounded-md border border-slate-200">
        {isLoading && <p className="px-3 py-2 text-sm text-slate-500">Buscando clientes...</p>}

        {!isLoading && error && (
          <p role="alert" className="px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {!isLoading && !error && clients.length === 0 && (
          <p className="px-3 py-2 text-sm text-slate-500">
            {search.trim()
              ? "Nenhum cliente encontrado com esse termo."
              : "Nenhum cliente cadastrado neste escritório ainda."}
          </p>
        )}

        {!isLoading &&
          !error &&
          clients.map((client) => (
            <button
              key={client.id}
              type="button"
              onClick={() => onSelect({ kind: "existing", client })}
              className="block w-full border-b border-slate-100 px-3 py-2 text-left last:border-b-0 hover:bg-slate-50"
            >
              <span className="block text-sm text-slate-900">{client.full_name}</span>
              <span className="block text-xs text-slate-500">
                {client.code}
                {client.document_number ? ` · ${formatDocument(client.document_number)}` : ""}
              </span>
            </button>
          ))}
      </div>

      <button
        type="button"
        onClick={onRequestNewClient}
        className="text-sm font-medium text-slate-700 underline hover:text-slate-900"
      >
        Cadastrar novo cliente
      </button>
    </div>
  );
}
