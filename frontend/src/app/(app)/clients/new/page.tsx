"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ClientForm } from "@/components/clients/ClientForm";
import { toClientPayload, type ClientFormValues } from "@/components/clients/clientSchema";
import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { useAuth } from "@/hooks/useAuth";
import { canWriteCase } from "@/lib/roles";
import { ApiError, api } from "@/services/api";

export default function NewClientPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);

  // O backend recusa de qualquer forma (403 em POST /clients) — isto só evita
  // que o advogado preencha a qualificação inteira para depois levar o erro.
  if (!canWriteCase(user)) {
    return (
      <AccessDeniedState
        message="Seu papel neste escritório permite apenas consultar clientes."
        backHref="/clients"
        backLabel="Voltar para Clientes"
      />
    );
  }

  async function handleSubmit(values: ClientFormValues) {
    setFormError(null);
    try {
      const created = await api.createClient(toClientPayload(values));
      router.push(`/clients/${created.id}`);
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : "Não foi possível cadastrar o cliente. Tente novamente.",
      );
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <Link href="/clients" className="text-sm text-slate-500 hover:text-slate-700">
          ← Voltar para Clientes
        </Link>
        <h1 className="mt-2 text-lg font-semibold text-slate-900">Novo cliente</h1>
        <p className="text-sm text-slate-500">
          A qualificação completa é o que a petição inicial exige (CPC art. 319, II). Só o nome é
          obrigatório agora — o resto pode ser complementado depois.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <ClientForm
          onSubmit={handleSubmit}
          onCancel={() => router.push("/clients")}
          formError={formError}
        />
      </div>
    </div>
  );
}
