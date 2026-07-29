"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { Case } from "@/types/api";

interface UseCasesResult {
  cases: Case[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useCases(): UseCasesResult {
  const [cases, setCases] = useState<Case[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.listCases();
        if (!cancelled) setCases(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar os casos.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { cases, isLoading, error, reload };
}
