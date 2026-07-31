"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { EvidenceAnalysisResult } from "@/types/api";

interface UseEvidenceAnalysisResult {
  analysis: EvidenceAnalysisResult | null;
  isLoading: boolean;
  error: string | null;
  /** true quando o backend respondeu 404 por a análise ainda não ter rodado (não é uma falha). */
  notRunYet: boolean;
  reload: () => void;
}

/** Carrega o resultado mais recente do módulo Evidence (GET .../evidence/analysis/result). */
export function useEvidenceAnalysis(caseId: string): UseEvidenceAnalysisResult {
  const [analysis, setAnalysis] = useState<EvidenceAnalysisResult | null>(null);
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
        const data = await api.getEvidenceAnalysis(caseId);
        if (!cancelled) setAnalysis(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotRunYet(true);
          setAnalysis(null);
        } else {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar a análise.",
          );
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

  return { analysis, isLoading, error, notRunYet, reload };
}
