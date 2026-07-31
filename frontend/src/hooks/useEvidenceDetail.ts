"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { EvidenceExtraction, EvidenceFile } from "@/types/api";

interface UseEvidenceDetailResult {
  evidence: EvidenceFile | null;
  extractions: EvidenceExtraction[];
  isLoading: boolean;
  error: string | null;
  notFound: boolean;
  /** true quando o backend negou a listagem de extrações (403 — papel viewer). */
  extractionsDenied: boolean;
  reload: () => void;
}

/**
 * Carrega uma evidência + suas execuções de extração (Fase 3.5).
 *
 * Metadados e extrações são carregados juntos; um 403 só nas extrações não
 * derruba a tela — o backend decide o que cada papel enxerga (CLAUDE.md,
 * seção 16: nenhuma autorização confiada só ao frontend).
 */
export function useEvidenceDetail(caseId: string, evidenceId: string): UseEvidenceDetailResult {
  const [evidence, setEvidence] = useState<EvidenceFile | null>(null);
  const [extractions, setExtractions] = useState<EvidenceExtraction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [extractionsDenied, setExtractionsDenied] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setNotFound(false);
      setExtractionsDenied(false);
      try {
        const evidenceData = await api.getEvidence(caseId, evidenceId);
        if (cancelled) return;
        setEvidence(evidenceData);
        try {
          const extractionData = await api.listEvidenceExtractions(caseId, evidenceId);
          if (!cancelled) setExtractions(extractionData);
        } catch (err) {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 403) {
            setExtractionsDenied(true);
          } else {
            throw err;
          }
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar a evidência.",
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
  }, [caseId, evidenceId, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { evidence, extractions, isLoading, error, notFound, extractionsDenied, reload };
}
