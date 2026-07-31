"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { EvidenceFile } from "@/types/api";

interface UseEvidenceListResult {
  evidence: EvidenceFile[];
  isLoading: boolean;
  error: string | null;
  /** true quando o backend negou o acesso (403) — não é a mesma coisa que erro de rede. */
  accessDenied: boolean;
  reload: () => void;
}

/** Carrega o inventário de evidências de um caso (GET .../evidence). */
export function useEvidenceList(caseId: string): UseEvidenceListResult {
  const [evidence, setEvidence] = useState<EvidenceFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setAccessDenied(false);
      try {
        const data = await api.listEvidence(caseId);
        if (!cancelled) setEvidence(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 403) {
          setAccessDenied(true);
        } else {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar as evidências.",
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

  return { evidence, isLoading, error, accessDenied, reload };
}
