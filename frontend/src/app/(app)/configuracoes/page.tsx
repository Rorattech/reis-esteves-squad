"use client";

import { useAuth } from "@/hooks/useAuth";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  lawyer: "Advogado(a)",
  paralegal: "Paralegal",
  viewer: "Leitor",
};

export default function ConfiguracoesPage() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-slate-900">Configurações</h1>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">Escritório</h2>
        <dl className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase text-slate-500">Nome</dt>
            <dd className="mt-1 text-sm text-slate-900">{user.tenant_name}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">Sua conta</h2>
        <dl className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase text-slate-500">E-mail</dt>
            <dd className="mt-1 text-sm text-slate-900">{user.email}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase text-slate-500">Papel</dt>
            <dd className="mt-1 text-sm text-slate-900">{ROLE_LABELS[user.role] ?? user.role}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
