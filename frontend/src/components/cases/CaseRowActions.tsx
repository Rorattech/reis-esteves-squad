"use client";

import { Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { MouseEvent } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ApiError, api } from "@/services/api";

interface CaseRowActionsProps {
  caseId: string;
  /** Só para identificar o caso na confirmação — o advogado precisa saber o que vai apagar. */
  caseLabel: string;
  canEdit: boolean;
  canDelete: boolean;
  /** Chamado depois que o backend confirma a exclusão — nunca antes. */
  onDeleted: () => void;
}

/**
 * Ações por linha da lista de casos (editar / excluir).
 *
 * A linha inteira da tabela navega para o caso, então todo clique aqui
 * precisa de `stopPropagation()`: sem isso, clicar em "Excluir" abriria o
 * caso por baixo do diálogo de confirmação.
 */
export function CaseRowActions({
  caseId,
  caseLabel,
  canEdit,
  canDelete,
  onDeleted,
}: CaseRowActionsProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function stopRowNavigation(event: MouseEvent) {
    event.stopPropagation();
  }

  async function handleDelete() {
    setConfirmOpen(false);
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteCase(caseId);
      onDeleted();
    } catch (error) {
      setDeleteError(
        error instanceof ApiError ? error.message : "Não foi possível excluir o caso.",
      );
    } finally {
      setIsDeleting(false);
    }
  }

  if (!canEdit && !canDelete) {
    return <span className="text-xs text-slate-400">—</span>;
  }

  return (
    <div className="flex items-center justify-end gap-1" onClick={stopRowNavigation}>
      {canEdit && (
        <Link
          href={`/cases/${caseId}/editar`}
          aria-label={`Editar caso ${caseLabel}`}
          title="Editar caso"
          onClick={stopRowNavigation}
          className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          <Pencil aria-hidden="true" className="h-4 w-4" />
        </Link>
      )}

      {canDelete && (
        <button
          type="button"
          disabled={isDeleting}
          aria-label={`Excluir caso ${caseLabel}`}
          title="Excluir caso"
          onClick={(event) => {
            stopRowNavigation(event);
            setConfirmOpen(true);
          }}
          className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
        >
          <Trash2 aria-hidden="true" className="h-4 w-4" />
        </button>
      )}

      {deleteError && (
        <p role="alert" className="ml-2 text-xs text-red-700">
          {deleteError}
        </p>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Excluir este caso?"
        description={`O caso "${caseLabel}" e todo o material ligado a ele — relato, checklist, evidências e histórico de etapas — são apagados. Esta ação não pode ser desfeita.`}
        confirmLabel="Excluir caso"
        cancelLabel="Cancelar"
        onConfirm={handleDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
