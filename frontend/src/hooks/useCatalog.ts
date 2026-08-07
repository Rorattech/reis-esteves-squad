"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { FraudModality, Platform } from "@/types/api";

interface UseCatalogResult {
  platforms: Platform[];
  modalities: FraudModality[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Carrega os catálogos de classificação do escritório (plataformas e
 * modalidades de golpe).
 *
 * As duas listas vêm juntas porque nenhuma tela usa uma sem a outra: o
 * formulário de caso classifica plataforma **e** modalidade de uma vez.
 */
export function useCatalog(): UseCatalogResult {
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [modalities, setModalities] = useState<FraudModality[]>([]);
  // Só a primeira carga liga o estado de carregamento — ver comentário no efeito.
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      // `isLoading` cobre apenas a primeira carga. Um reload — disparado ao
      // cadastrar uma entrada nova pela opção "Outro" — não pode voltar a
      // true: as telas escondem o formulário enquanto carrega, e desmontá-lo
      // apagaria o cliente já escolhido e o resto do que o advogado preencheu.
      setError(null);
      try {
        const [platformList, modalityList] = await Promise.all([
          api.listPlatforms(),
          api.listFraudModalities(),
        ]);
        if (!cancelled) {
          setPlatforms(platformList);
          setModalities(modalityList);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar o catálogo.",
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
  }, [reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { platforms, modalities, isLoading, error, reload };
}
