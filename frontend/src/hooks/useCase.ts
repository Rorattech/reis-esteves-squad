"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { Case } from "@/types/api";

interface UseCaseResult {
  case: Case | null;
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useCase(caseId: string): UseCaseResult {
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.getCase(caseId);
        if (!cancelled) setCaseData(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar o caso.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [caseId, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { case: caseData, isLoading, error, reload };
}
