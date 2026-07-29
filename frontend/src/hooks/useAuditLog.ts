"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { AuditLogEntry } from "@/types/api";

interface UseAuditLogResult {
  entries: AuditLogEntry[];
  isLoading: boolean;
  error: string | null;
  /** true quando o backend respondeu 403 — restrito a admin/lawyer/paralegal, ver app/api/v1/intake.py. */
  forbidden: boolean;
  reload: () => void;
}

/** Carrega o histórico de auditoria de um caso (GET .../audit-log). */
export function useAuditLog(caseId: string): UseAuditLogResult {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setForbidden(false);
      try {
        const data = await api.getAuditLog(caseId);
        if (!cancelled) setEntries(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 403) {
            setForbidden(true);
          } else {
            setError(
              err instanceof ApiError ? err.message : "Não foi possível carregar o histórico.",
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

  return { entries, isLoading, error, forbidden, reload };
}
