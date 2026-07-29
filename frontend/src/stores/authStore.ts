import { create } from "zustand";

import type { User } from "@/types/api";

export type AuthStatus = "idle" | "checking" | "authenticated" | "unauthenticated";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  status: AuthStatus;
  setSession: (accessToken: string, user: User) => void;
  setAccessToken: (accessToken: string) => void;
  setStatus: (status: AuthStatus) => void;
  clear: () => void;
}

/**
 * Estado global de autenticação (CLAUDE.md, seção 6 — Zustand, não Redux).
 *
 * O access token vive só em memória (nunca em localStorage) — é perdido em
 * um reload de página de propósito, e recuperado via refresh token (ver
 * REFRESH_TOKEN_STORAGE_KEY abaixo). docs/architecture.md descreve JWT em
 * cookie HttpOnly; o backend atual devolve os tokens no corpo da resposta,
 * não via Set-Cookie — esta é uma simplificação deliberada para a fundação,
 * não a forma final. Reforçar para HttpOnly cookie é trabalho futuro.
 */
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: "idle",
  setSession: (accessToken, user) => set({ accessToken, user, status: "authenticated" }),
  setAccessToken: (accessToken) => set({ accessToken }),
  setStatus: (status) => set({ status }),
  clear: () => set({ accessToken: null, user: null, status: "unauthenticated" }),
}));

const REFRESH_TOKEN_STORAGE_KEY = "squad_digital.refresh_token";

export function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
}

export function storeRefreshToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token);
}

export function clearStoredRefreshToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}
