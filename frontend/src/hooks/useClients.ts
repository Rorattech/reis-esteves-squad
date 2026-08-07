"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { Client } from "@/types/api";

interface UseClientsResult {
  clients: Client[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/** Atraso antes de buscar, para não disparar uma request por tecla digitada. */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Busca clientes do escritório por nome, CPF/CNPJ ou código.
 *
 * A busca é do servidor (`GET /clients?search=`), não do navegador: a base de
 * clientes cresce sem teto e cada nome baixado é dado pessoal em memória.
 */
export function useClients(search: string = ""): UseClientsResult {
  const [clients, setClients] = useState<Client[]>([]);
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
        const data = await api.listClients(search);
        if (!cancelled) setClients(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar os clientes.",
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { clients, isLoading, error, reload };
}

interface UseClientResult {
  client: Client | null;
  isLoading: boolean;
  error: string | null;
  /** true quando o backend respondeu 404 — inexistente ou de outro tenant. */
  notFound: boolean;
  reload: () => void;
}

export function useClient(clientId: string): UseClientResult {
  const [client, setClient] = useState<Client | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const data = await api.getClient(clientId);
        if (!cancelled) setClient(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setNotFound(true);
          } else {
            setError(
              err instanceof ApiError ? err.message : "Não foi possível carregar o cliente.",
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
  }, [clientId, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { client, isLoading, error, notFound, reload };
}
