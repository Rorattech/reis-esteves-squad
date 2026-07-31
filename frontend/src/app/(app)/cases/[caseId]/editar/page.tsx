"use client";

import { useParams } from "next/navigation";

import { CaseEditForm } from "@/components/cases/CaseEditForm";
import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";
import { useCase } from "@/hooks/useCase";
import { canWriteCase } from "@/lib/roles";

/**
 * Edição do cadastro do caso — o que foi informado na abertura (inclusive
 * token do cliente, área e matéria) continua visível e corrigível depois.
 *
 * Esta página só carrega e decide o que mostrar; o formulário em si é
 * `CaseEditForm`, montado apenas com o caso já carregado.
 */
export default function EditCasePage() {
  const params = useParams<{ caseId: string }>();
  const { user } = useAuth();
  const { case: caseData, isLoading, error, notFound, reload } = useCase(params.caseId);

  if (isLoading) return <LoadingState label="Carregando caso..." />;
  if (notFound) return <AccessDeniedState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!caseData) return null;
  // O backend rejeita com 403 de qualquer forma — a UI só evita oferecer uma
  // edição que vai falhar (CLAUDE.md, seção 16).
  if (!canWriteCase(user)) return <AccessDeniedState />;

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Editar caso</h1>
        <p className="text-sm text-slate-500">
          Corrija os dados de cadastro do caso. Status e etapa não são editados aqui — mudam pelas
          decisões registradas no fluxo do caso.
        </p>
      </div>

      <CaseEditForm caseData={caseData} />
    </div>
  );
}
