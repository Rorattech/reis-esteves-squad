"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { CaseDocument } from "@/types/api";

interface UseCaseDocumentsResult {
  documents: CaseDocument[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/** Carrega o checklist de documentos de um caso (GET .../documents). */
export function useCaseDocuments(caseId: string): UseCaseDocumentsResult {
  const [documents, setDocuments] = useState<CaseDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.listCaseDocuments(caseId);
        if (!cancelled) setDocuments(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar o checklist.");
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

  return { documents, isLoading, error, reload };
}
