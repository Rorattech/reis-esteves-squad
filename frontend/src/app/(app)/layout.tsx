"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";

/**
 * Casca do layout autenticado (barra lateral + cabeçalho + conteúdo). Toda
 * rota dentro do grupo `(app)` passa por aqui — nenhuma delas verifica auth
 * por conta própria (CLAUDE.md, seção 16 — autorização nunca só no cliente,
 * mas a UI ainda precisa redirecionar antes de tentar renderizar dado
 * protegido; o backend continua sendo a fonte de verdade da autorização).
 */
export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { isAuthenticated, isChecking, user, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isChecking && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isChecking, isAuthenticated, router]);

  if (isChecking || !isAuthenticated || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <LoadingState label="Verificando sessão..." />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Header user={user} onLogout={logout} />
        <main className="flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
