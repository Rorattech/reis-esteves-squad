"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { IntakeResult } from "@/types/api";

interface UseIntakeResultResult {
  result: IntakeResult | null;
  isLoading: boolean;
  error: string | null;
  /** true quando o backend respondeu 404 por o Intake ainda não ter sido executado (não é uma falha). */
  notRunYet: boolean;
  reload: () => void;
}

/** Carrega o resultado mais recente de coordinator+triage (GET .../intake/result). */
export function useIntakeResult(caseId: string): UseIntakeResultResult {
  const [result, setResult] = useState<IntakeResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notRunYet, setNotRunYet] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setNotRunYet(false);
      try {
        const data = await api.getIntakeResult(caseId);
        if (!cancelled) setResult(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setNotRunYet(true);
          } else {
            setError(
              err instanceof ApiError ? err.message : "Não foi possível carregar o resultado da triagem.",
            );
          }
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

  return { result, isLoading, error, notRunYet, reload };
}
