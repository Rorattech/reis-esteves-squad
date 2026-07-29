"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { CaseIntake } from "@/types/api";

interface UseCaseIntakeResult {
  intake: CaseIntake | null;
  isLoading: boolean;
  error: string | null;
  /** true quando o backend respondeu 404 por ainda não haver relato registrado (não é uma falha). */
  notSubmittedYet: boolean;
  reload: () => void;
}

/** Carrega o relato inicial de um caso (GET .../intake) — ver app/api/v1/intake.py. */
export function useCaseIntake(caseId: string): UseCaseIntakeResult {
  const [intake, setIntake] = useState<CaseIntake | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notSubmittedYet, setNotSubmittedYet] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setNotSubmittedYet(false);
      try {
        const data = await api.getCaseIntake(caseId);
        if (!cancelled) setIntake(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setNotSubmittedYet(true);
          } else {
            setError(
              err instanceof ApiError ? err.message : "Não foi possível carregar o relato inicial.",
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

  return { intake, isLoading, error, notSubmittedYet, reload };
}
