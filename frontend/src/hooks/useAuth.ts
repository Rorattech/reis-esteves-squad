"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/services/api";
import {
  clearStoredRefreshToken,
  getStoredRefreshToken,
  storeRefreshToken,
  useAuthStore,
} from "@/stores/authStore";

/**
 * Restaura a sessão a partir do refresh token salvo — exatamente uma vez por
 * carregamento de página, não uma vez por componente.
 *
 * `useAuth()` é chamado por vários componentes ao mesmo tempo (o layout
 * autenticado E cada página, ver app/(app)/**). Cada chamada tem seu próprio
 * useEffect; sem esse cache em escopo de módulo, cada nova instância do hook
 * (ex.: ao navegar para uma página que também usa useAuth) reiniciava a
 * restauração do zero e derrubava o status de volta para "checking".
 */
let restoreOnce: Promise<void> | null = null;

function restoreSession(): Promise<void> {
  if (!restoreOnce) {
    restoreOnce = (async () => {
      const store = useAuthStore.getState();
      store.setStatus("checking");

      if (!getStoredRefreshToken()) {
        store.setStatus("unauthenticated");
        return;
      }

      const newAccessToken = await api.restoreSession();
      if (!newAccessToken) {
        store.setStatus("unauthenticated");
        return;
      }

      try {
        const me = await api.getMe();
        useAuthStore.getState().setSession(newAccessToken, me);
      } catch {
        clearStoredRefreshToken();
        useAuthStore.getState().setStatus("unauthenticated");
      }
    })();
  }
  return restoreOnce;
}

/**
 * Orquestra login/logout/restauração de sessão. Nenhum componente deve ler
 * localStorage ou chamar `api` de autenticação diretamente — sempre via este
 * hook (CLAUDE.md, seção 6 — sem lógica de negócio em componentes).
 */
export function useAuth() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const setSession = useAuthStore((state) => state.setSession);
  const clear = useAuthStore((state) => state.clear);
  const router = useRouter();

  useEffect(() => {
    void restoreSession();
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.login(email, password);
      useAuthStore.getState().setAccessToken(tokens.access_token);
      if (tokens.refresh_token) storeRefreshToken(tokens.refresh_token);
      const me = await api.getMe();
      setSession(tokens.access_token, me);
    },
    [setSession],
  );

  const logout = useCallback(() => {
    clearStoredRefreshToken();
    clear();
    router.replace("/login");
  }, [clear, router]);

  return {
    user,
    accessToken,
    status,
    isAuthenticated: status === "authenticated",
    isChecking: status === "idle" || status === "checking",
    login,
    logout,
  };
}
