"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { Case, CaseStatus } from "@/types/api";

interface UseCasesParams {
  search?: string;
  /** "all" (ou ausente) não filtra por status. */
  status?: CaseStatus | "all";
}

interface UseCasesResult {
  cases: Case[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/** Atraso antes de buscar, para não disparar uma request por tecla digitada. */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Lista os casos do escritório, com busca e filtro aplicados no servidor.
 *
 * A busca deixou de ser do navegador na Fase 2.7: ela passou a incluir o nome
 * do cliente, e filtrar localmente exigiria baixar a base de casos inteira —
 * com os nomes — para toda sessão aberta.
 */
export function useCases({ search = "", status = "all" }: UseCasesParams = {}): UseCasesResult {
  const [cases, setCases] = useState<Case[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    // setIsLoading dentro do timer, não no corpo do efeito: a busca é
    // debounced, então o carregamento começa quando a request começa — não a
    // cada tecla digitada (e o corpo do efeito não dispara render em cascata).
    const timer = setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.listCases({
          search,
          status: status === "all" ? undefined : status,
        });
        if (!cancelled) setCases(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar os casos.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search, status, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { cases, isLoading, error, reload };
}
