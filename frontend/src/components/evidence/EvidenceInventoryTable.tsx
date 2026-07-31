"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { EVIDENCE_STATUS_LABELS } from "@/lib/caseLabels";
import { api, ApiError } from "@/services/api";
import type { EvidenceFile, EvidenceProcessingStatus } from "@/types/api";

const STATUS_STYLES: Record<EvidenceProcessingStatus, string> = {
  received: "bg-slate-100 text-slate-700",
  processing: "bg-blue-100 text-blue-700",
  processed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

function formatBytes(size: number): string {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${size} B`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

interface EvidenceInventoryTableProps {
  caseId: string;
  evidence: EvidenceFile[];
  canWrite: boolean;
  onChanged: () => void;
}

/**
 * Inventário de evidências (roadmap 3.4): status real de processamento,
 * origem e duplicidade vêm sempre do backend — o frontend não calcula nem
 * declara integridade de arquivo. Download só por rota autenticada (cada
 * acesso é auditado no backend); nunca há URL pública permanente.
 */
export function EvidenceInventoryTable({
  caseId,
  evidence,
  canWrite,
  onChanged,
}: EvidenceInventoryTableProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function download(item: EvidenceFile) {
    setActionError(null);
    setBusyId(item.id);
    try {
      const blob = await api.downloadEvidence(caseId, item.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = item.original_filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível baixar o arquivo.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function reprocess(item: EvidenceFile) {
    setActionError(null);
    setBusyId(item.id);
    try {
      await api.processEvidence(caseId, item.id);
      onChanged();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível reprocessar a evidência.",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (evidence.length === 0) {
    return (
      <EmptyState
        title="Nenhuma evidência anexada ainda"
        description="Envie prints, comprovantes, PDFs ou exportações de conversa para montar a pasta probatória do caso."
      />
    );
  }

  return (
    <div className="space-y-2">
      {actionError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
      )}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Arquivo</th>
              <th scope="col" className="px-4 py-2">Status</th>
              <th scope="col" className="px-4 py-2">Origem</th>
              <th scope="col" className="px-4 py-2">Recebido em</th>
              <th scope="col" className="px-4 py-2">
                <span className="sr-only">Ações</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {evidence.map((item) => (
              <tr key={item.id}>
                <td className="px-4 py-3">
                  <p className="font-medium text-slate-900">{item.original_filename}</p>
                  <p className="text-xs text-slate-500">
                    {item.mime_type} · {formatBytes(item.size_bytes)}
                    {item.is_duplicate && (
                      <span className="ml-2 inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                        Duplicado
                      </span>
                    )}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status]}`}
                  >
                    {EVIDENCE_STATUS_LABELS[item.status]}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{item.origin}</td>
                <td className="px-4 py-3 text-slate-600">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <Link
                      href={`/cases/${caseId}/evidencias/${item.id}`}
                      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Detalhe
                    </Link>
                    {canWrite && (
                      <>
                        <button
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() => download(item)}
                          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          Baixar
                        </button>
                        <button
                          type="button"
                          disabled={busyId === item.id || item.status === "processing"}
                          onClick={() => reprocess(item)}
                          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          Reprocessar
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
