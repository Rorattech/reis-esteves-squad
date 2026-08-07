"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";
import { useClients } from "@/hooks/useClients";
import { PERSON_TYPE_LABELS } from "@/lib/caseLabels";
import { formatDocument } from "@/lib/documents";
import { canWriteCase } from "@/lib/roles";

export default function ClientsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const { clients, isLoading, error, reload } = useClients(search);

  // Esconder a ação que o papel não pode executar é conveniência de UX — o
  // backend reforça a autorização de verdade (CLAUDE.md, seção 16).
  const canCreateClient = canWriteCase(user);

  const hasActiveSearch = search.trim().length > 0;
  const isEmptyOffice = clients.length === 0 && !hasActiveSearch;

  const newClientButton = canCreateClient ? (
    <Link
      href="/clients/new"
      className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
    >
      Novo cliente
    </Link>
  ) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Clientes</h1>
        {newClientButton}
      </div>

      {isLoading && <LoadingState label="Carregando clientes..." />}

      {!isLoading && error && <ErrorState message={error} onRetry={reload} />}

      {!isLoading && !error && isEmptyOffice && (
        <EmptyState
          title="Nenhum cliente cadastrado"
          description="Cadastre o cliente aqui ou na abertura de um caso — os dois caminhos levam ao mesmo cadastro."
          action={newClientButton ?? undefined}
        />
      )}

      {!isLoading && !error && !isEmptyOffice && (
        <>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome, CPF/CNPJ ou código..."
            aria-label="Buscar clientes"
            className="w-80 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          />

          {clients.length === 0 ? (
            <EmptyState
              title="Nenhum cliente encontrado"
              description="Ajuste a busca para ver outros clientes."
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Código</th>
                    <th className="px-4 py-3 font-medium">Nome</th>
                    <th className="px-4 py-3 font-medium">Natureza</th>
                    <th className="px-4 py-3 font-medium">CPF / CNPJ</th>
                    <th className="px-4 py-3 font-medium">Município</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {clients.map((client) => (
                    <tr
                      key={client.id}
                      onClick={() => router.push(`/clients/${client.id}`)}
                      className="cursor-pointer hover:bg-slate-50"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/clients/${client.id}`}
                          className="font-medium text-slate-900 hover:underline"
                        >
                          {client.code}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-900">{client.full_name}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {PERSON_TYPE_LABELS[client.person_type]}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {formatDocument(client.document_number)}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {client.address_city
                          ? `${client.address_city}${client.address_state ? `/${client.address_state}` : ""}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
