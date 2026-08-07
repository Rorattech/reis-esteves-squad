"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useCases } from "@/hooks/useCases";
import { useClient } from "@/hooks/useClients";
import { MARITAL_STATUS_LABELS, PERSON_TYPE_LABELS } from "@/lib/caseLabels";
import { formatDocument, formatZipCode } from "@/lib/documents";
import type { Client } from "@/types/api";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-900">{value || "—"}</dd>
    </div>
  );
}

function formatAddress(client: Client): string | null {
  const street = [client.address_street, client.address_number].filter(Boolean).join(", ");
  const line = [street, client.address_complement, client.address_district]
    .filter(Boolean)
    .join(" · ");
  return line || null;
}

export default function ClientDetailPage() {
  // useParams, e não `use(params)`: mesmo padrão das telas de caso
  // (cases/[caseId]/page.tsx).
  const params = useParams<{ clientId: string }>();
  const { client, isLoading, error, notFound, reload } = useClient(params.clientId);
  // Busca pelo código do cliente: `GET /cases?search=` casa com Client.code.
  const { cases, isLoading: isLoadingCases } = useCases({ search: client?.code ?? "" });

  if (isLoading) return <LoadingState label="Carregando cliente..." />;

  if (notFound) {
    return (
      <AccessDeniedState
        message="Este cliente não existe ou você não tem acesso a ele."
        backHref="/clients"
        backLabel="Voltar para Clientes"
      />
    );
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!client) return null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/clients" className="text-sm text-slate-500 hover:text-slate-700">
          ← Voltar para Clientes
        </Link>
        <h1 className="mt-2 text-lg font-semibold text-slate-900">{client.full_name}</h1>
        <p className="text-sm text-slate-500">
          {client.code} · {PERSON_TYPE_LABELS[client.person_type]}
        </p>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-medium text-slate-900">Qualificação</h2>
        <dl className="mt-3 grid gap-4 sm:grid-cols-3">
          <Field
            label={client.person_type === "company" ? "CNPJ" : "CPF"}
            value={formatDocument(client.document_number)}
          />
          <Field label="RG" value={client.rg} />
          <Field label="Órgão emissor" value={client.rg_issuer} />
          <Field
            label="Nascimento"
            value={
              client.birth_date ? new Date(client.birth_date).toLocaleDateString("pt-BR") : null
            }
          />
          <Field label="Nacionalidade" value={client.nationality} />
          <Field
            label="Estado civil"
            value={client.marital_status ? MARITAL_STATUS_LABELS[client.marital_status] : null}
          />
          <Field label="Profissão" value={client.profession} />
          <Field label="E-mail" value={client.email} />
          <Field label="Telefone" value={client.phone} />
        </dl>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-medium text-slate-900">Endereço</h2>
        <p className="mt-1 text-xs text-slate-500">
          O município define o foro do consumidor (CDC art. 101, I) — é o único dado do cliente que
          o sistema envia aos agentes de IA.
        </p>
        <dl className="mt-3 grid gap-4 sm:grid-cols-3">
          <Field label="Logradouro" value={formatAddress(client)} />
          <Field
            label="Município / UF"
            value={
              client.address_city
                ? `${client.address_city}${client.address_state ? `/${client.address_state}` : ""}`
                : null
            }
          />
          <Field label="CEP" value={formatZipCode(client.address_zip_code)} />
        </dl>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-medium text-slate-900">Casos deste cliente</h2>

        {isLoadingCases && <LoadingState label="Carregando casos..." />}

        {!isLoadingCases && cases.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">
            Nenhum caso aberto para este cliente ainda.
          </p>
        )}

        {!isLoadingCases && cases.length > 0 && (
          <ul className="mt-3 divide-y divide-slate-100">
            {cases.map((item) => (
              <li key={item.id} className="flex items-center justify-between py-2">
                <div>
                  <Link
                    href={`/cases/${item.id}`}
                    className="text-sm font-medium text-slate-900 hover:underline"
                  >
                    {item.code}
                  </Link>
                  <p className="text-xs text-slate-500">
                    {item.platform} · {item.fraud_modality.label}
                  </p>
                </div>
                <StatusBadge status={item.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
