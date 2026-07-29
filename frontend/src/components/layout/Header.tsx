"use client";

import type { User } from "@/types/api";

const ROLE_LABELS: Record<User["role"], string> = {
  admin: "Administrador",
  lawyer: "Advogado(a)",
  paralegal: "Paralegal",
  viewer: "Leitor",
};

interface HeaderProps {
  user: User;
  onLogout: () => void;
}

export function Header({ user, onLogout }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <p className="text-sm font-semibold text-slate-900">{user.tenant_name}</p>

      <div className="flex items-center gap-4">
        <button
          type="button"
          aria-label="Notificações"
          title="Nenhuma notificação por enquanto"
          className="rounded-full p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
            <path d="M10 2a6 6 0 0 0-6 6v3.586l-.707.707A1 1 0 0 0 4 14h12a1 1 0 0 0 .707-1.707L16 11.586V8a6 6 0 0 0-6-6ZM8.05 16a1.5 1.5 0 0 0 2.9 0h-2.9Z" />
          </svg>
        </button>

        <div className="text-right leading-tight">
          <p className="text-sm font-medium text-slate-900">{user.email}</p>
          <p className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</p>
        </div>

        <button
          type="button"
          onClick={onLogout}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Sair
        </button>
      </div>
    </header>
  );
}
