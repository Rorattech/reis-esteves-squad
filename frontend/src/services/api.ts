/**
 * Chamadas de API centralizadas (CLAUDE.md, seção 6). Nenhum componente ou
 * hook deve chamar `fetch` diretamente contra o backend — sempre via `api`.
 */

import {
  clearStoredRefreshToken,
  getStoredRefreshToken,
  useAuthStore,
} from "@/stores/authStore";
import type { Case, CaseCreateInput, TokenResponse, User } from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ");
    }
  } catch {
    // corpo da resposta não é JSON — segue com a mensagem genérica abaixo.
  }
  return `Erro inesperado (HTTP ${response.status}).`;
}

/**
 * Renova o access token a partir do refresh token guardado localmente.
 *
 * Usado tanto na restauração de sessão ao carregar a página quanto no retry
 * automático de uma request que voltou 401 (ver `request` abaixo). Só uma
 * chamada de refresh corre por vez — `inflightRefresh` deduplica retries
 * concorrentes (ex.: várias requests em paralelo recebendo 401 juntas).
 */
let inflightRefresh: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clearStoredRefreshToken();
    return null;
  }
  const tokens: TokenResponse = await response.json();
  useAuthStore.getState().setAccessToken(tokens.access_token);
  return tokens.access_token;
}

function refreshAccessTokenOnce(): Promise<string | null> {
  if (!inflightRefresh) {
    inflightRefresh = refreshAccessToken().finally(() => {
      inflightRefresh = null;
    });
  }
  return inflightRefresh;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  { allowRefreshRetry = true }: { allowRefreshRetry?: boolean } = {},
): Promise<T> {
  const accessToken = useAuthStore.getState().accessToken;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

  if (response.status === 401 && allowRefreshRetry) {
    const newAccessToken = await refreshAccessTokenOnce();
    if (newAccessToken) {
      return request<T>(path, options, { allowRefreshRetry: false });
    }
    useAuthStore.getState().clear();
    throw new ApiError(401, "Sessão expirada. Faça login novamente.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  async login(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { allowRefreshRetry: false },
    );
  },

  /** Restaura a sessão a partir do refresh token salvo (ex.: ao recarregar a página). */
  restoreSession: refreshAccessToken,

  async getMe(): Promise<User> {
    return request<User>("/auth/me");
  },

  async listCases(): Promise<Case[]> {
    return request<Case[]>("/cases");
  },

  async getCase(caseId: string): Promise<Case> {
    return request<Case>(`/cases/${caseId}`);
  },

  async createCase(input: CaseCreateInput): Promise<Case> {
    return request<Case>("/cases", { method: "POST", body: JSON.stringify(input) });
  },
};
