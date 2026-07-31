"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { EvidenceFile } from "@/types/api";

interface EvidenceOriginalViewerProps {
  caseId: string;
  evidence: EvidenceFile;
  /** Papel viewer não baixa o conteúdo original (403 no backend). */
  canReadOriginal: boolean;
}

/**
 * Visualização protegida do original (roadmap 3.5): o conteúdo chega por
 * rota autenticada como Blob e vira uma object URL efêmera do navegador —
 * nunca existe URL pública permanente, e cada acesso é auditado no backend
 * (cadeia de custódia).
 */
export function EvidenceOriginalViewer({
  caseId,
  evidence,
  canReadOriginal,
}: EvidenceOriginalViewerProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isImage = evidence.mime_type.startsWith("image/");
  const isPdf = evidence.mime_type === "application/pdf";
  const viewable = isImage || isPdf;

  useEffect(() => {
    if (!canReadOriginal || !viewable) return;
    let cancelled = false;
    let url: string | null = null;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const blob = await api.downloadEvidence(caseId, evidence.id);
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setObjectUrl(url);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Não foi possível carregar o original.",
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [caseId, evidence.id, canReadOriginal, viewable]);

  async function downloadOriginal() {
    setError(null);
    try {
      const blob = await api.downloadEvidence(caseId, evidence.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = evidence.original_filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível baixar o original.");
    }
  }

  if (!canReadOriginal) {
    return (
      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
        Seu papel atual permite consultar os metadados, mas não o conteúdo original do arquivo.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {isLoading && <p className="text-sm text-slate-500">Carregando original...</p>}

      {viewable && objectUrl && isImage && (
        // eslint-disable-next-line @next/next/no-img-element -- object URL efêmera de blob autenticado; next/image não se aplica.
        <img
          src={objectUrl}
          alt={`Original da evidência ${evidence.original_filename}`}
          className="max-h-[480px] rounded-lg border border-slate-200 object-contain"
        />
      )}
      {viewable && objectUrl && isPdf && (
        <iframe
          src={objectUrl}
          title={`Original da evidência ${evidence.original_filename}`}
          className="h-[480px] w-full rounded-lg border border-slate-200"
        />
      )}
      {!viewable && (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Este tipo de arquivo ({evidence.mime_type}) não tem visualização embutida — use o
          download para conferir o original.
        </p>
      )}

      <button
        type="button"
        onClick={downloadOriginal}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Baixar original ({evidence.original_filename})
      </button>
    </div>
  );
}
