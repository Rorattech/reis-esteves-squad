"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useCaseDocuments } from "@/hooks/useCaseDocuments";
import { DOCUMENT_STATUS_LABELS } from "@/lib/caseLabels";
import { ApiError, api } from "@/services/api";
import type { DocumentChecklistStatus } from "@/types/api";

const STATUS_OPTIONS = Object.entries(DOCUMENT_STATUS_LABELS) as [DocumentChecklistStatus, string][];

interface CaseDocumentChecklistProps {
  caseId: string;
  canWrite: boolean;
  /** Nomes recomendados pela triagem mais recente (IntakeResult.documents_requested) que ainda não estão no checklist. */
  suggestedFromTriage?: string[];
}

/**
 * Checklist estruturado de documentos (GET/POST/PATCH .../documents,
 * backend/app/models/schemas/case_document.py) — distinto de
 * `claimed_documents` do relato inicial (o que o cliente *diz* ter, sem
 * status nem rastreio). `suggestedFromTriage` é só uma sugestão de nomes a
 * adicionar; nunca é criado sozinho no checklist (docs/intake_graph_flow.md:
 * "materializar isso em linhas de CaseDocument é responsabilidade de quem
 * chama o grafo", aqui a interface, sob confirmação do advogado).
 */
export function CaseDocumentChecklist({
  caseId,
  canWrite,
  suggestedFromTriage = [],
}: CaseDocumentChecklistProps) {
  const { documents, isLoading, error, reload } = useCaseDocuments(caseId);
  const [newItemName, setNewItemName] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingName, setPendingName] = useState<string | null>(null);

  const existingNames = new Set(documents.map((item) => item.name.trim().toLowerCase()));
  const suggestions = suggestedFromTriage.filter(
    (name) => !existingNames.has(name.trim().toLowerCase()),
  );

  async function addDocument(name: string) {
    if (!name.trim()) return;
    setActionError(null);
    setPendingName(name);
    try {
      await api.addCaseDocument(caseId, { name: name.trim() });
      setNewItemName("");
      reload();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível adicionar o documento.",
      );
    } finally {
      setPendingName(null);
    }
  }

  async function updateStatus(documentId: string, status: DocumentChecklistStatus) {
    setActionError(null);
    try {
      await api.updateCaseDocument(caseId, documentId, { status });
      reload();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Não foi possível atualizar o documento.",
      );
    }
  }

  if (isLoading) return <LoadingState label="Carregando checklist..." />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  return (
    <div className="space-y-3">
      {actionError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</p>
      )}

      {suggestions.length > 0 && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3">
          <p className="text-xs font-medium uppercase text-blue-700">Sugeridos pela triagem</p>
          <ul className="mt-2 space-y-1">
            {suggestions.map((name) => (
              <li key={name} className="flex items-center justify-between gap-2 text-sm text-blue-900">
                <span>{name}</span>
                {canWrite && (
                  <button
                    type="button"
                    disabled={pendingName === name}
                    onClick={() => addDocument(name)}
                    className="rounded-md border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
                  >
                    {pendingName === name ? "Adicionando..." : "Adicionar ao checklist"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {documents.length === 0 ? (
        <EmptyState
          title="Nenhum documento no checklist ainda"
          description="Adicione manualmente ou aceite uma sugestão da triagem."
        />
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {documents.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-slate-900">{item.name}</p>
                {item.notes && <p className="text-xs text-slate-500">{item.notes}</p>}
              </div>
              {canWrite ? (
                <select
                  value={item.status}
                  aria-label={`Status de ${item.name}`}
                  onChange={(event) =>
                    updateStatus(item.id, event.target.value as DocumentChecklistStatus)
                  }
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs focus:border-slate-500 focus:outline-none"
                >
                  {STATUS_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="text-xs text-slate-500">{DOCUMENT_STATUS_LABELS[item.status]}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {canWrite && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            addDocument(newItemName);
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={newItemName}
            onChange={(event) => setNewItemName(event.target.value)}
            placeholder="Nome do documento..."
            aria-label="Nome do novo documento"
            className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={newItemName.trim().length === 0 || pendingName !== null}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Adicionar
          </button>
        </form>
      )}
    </div>
  );
}
