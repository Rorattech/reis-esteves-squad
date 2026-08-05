"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { AdvanceStageAction } from "@/components/cases/AdvanceStageAction";
import { AuditLogTimeline } from "@/components/cases/AuditLogTimeline";
import { IntakeNarrativeForm } from "@/components/cases/IntakeNarrativeForm";
import { IntakeResultPanel } from "@/components/cases/IntakeResultPanel";
import { IntakeReviewForm } from "@/components/cases/IntakeReviewForm";
import { RunTriageAction } from "@/components/cases/RunTriageAction";
import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";
import { useCase } from "@/hooks/useCase";
import { useCaseIntake } from "@/hooks/useCaseIntake";
import { useIntakeResult } from "@/hooks/useIntakeResult";
import { canWriteCase } from "@/lib/roles";

/**
 * Aba Intake (docs/roadmap_mvp_squad_digital.md, 2.6) — onde o humano no
 * loop existe de verdade: relato → triagem → resultado → aprovar/corrigir/
 * devolver. Cada ação re-carrega caso/relato/resultado/checklist/histórico
 * a partir do backend (nunca atualiza a UI de forma otimista — a
 * classificação e a decisão de avançar são sempre do servidor).
 */
export default function CaseIntakePage() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const { user } = useAuth();
  const canWrite = canWriteCase(user);

  const {
    case: caseData,
    isLoading: caseLoading,
    error: caseError,
    notFound,
    reload: reloadCase,
  } = useCase(caseId);
  const {
    intake,
    isLoading: intakeLoading,
    error: intakeError,
    reload: reloadIntake,
  } = useCaseIntake(caseId);
  const {
    result,
    isLoading: resultLoading,
    error: resultError,
    notRunYet,
    reload: reloadResult,
  } = useIntakeResult(caseId);

  const [historyVersion, setHistoryVersion] = useState(0);
  const [checklistVersion, setChecklistVersion] = useState(0);

  function refreshEverything() {
    reloadCase();
    reloadIntake();
    reloadResult();
    setHistoryVersion((version) => version + 1);
    setChecklistVersion((version) => version + 1);
  }

  if (caseLoading || intakeLoading) {
    return <LoadingState label="Carregando intake..." />;
  }
  if (notFound) return <AccessDeniedState />;
  if (caseError) return <ErrorState message={caseError} onRetry={reloadCase} />;
  if (intakeError) return <ErrorState message={intakeError} onRetry={reloadIntake} />;
  if (!caseData) return null;

  return (
    <div className="space-y-8">
      <section>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Passo 1 de 3</p>
        <h2 className="text-base font-semibold text-slate-900">Relato inicial</h2>
        <p className="mt-1 text-sm text-slate-500">
          Texto livre do cliente + campos estruturados coletados no primeiro contato. Sem o relato
          salvo, os passos 2 e 3 ficam bloqueados.
        </p>
        <div className="mt-3">
          <IntakeNarrativeForm
            caseData={caseData}
            intake={intake}
            canWrite={canWrite}
            onSaved={refreshEverything}
          />
        </div>
      </section>

      <section>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Passo 2 de 3 · opcional
        </p>
        <h2 className="text-base font-semibold text-slate-900">Triagem</h2>
        <p className="mt-1 text-sm text-slate-500">
          Classifica plataforma, modalidade e urgência, e monta o checklist de documentos — sempre
          como recomendação revisável. Se você preferir conduzir a abertura sem a IA, pule para o
          passo 3.
        </p>
        <div className="mt-3 space-y-4">
          <RunTriageAction
            caseId={caseId}
            hasIntake={intake !== null}
            canWrite={canWrite}
            onCompleted={refreshEverything}
          />
          <IntakeResultPanel
            result={result}
            isLoading={resultLoading}
            error={resultError}
            notRunYet={notRunYet}
            onRetry={reloadResult}
            caseId={caseId}
            canWrite={canWrite}
            checklistVersion={checklistVersion}
          />
        </div>
      </section>

      <section>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Passo 3 de 3</p>
        <h2 className="text-base font-semibold text-slate-900">Revisão humana</h2>
        <p className="mt-1 text-sm text-slate-500">
          É aqui que o caso passa de fase: aprovar ou corrigir a recomendação da triagem — ou
          concluir a abertura manualmente, quando não há recomendação a revisar — libera a etapa de
          Evidências. Devolver para complementação mantém o caso nesta etapa.
        </p>
        <div className="mt-3 space-y-4">
          <IntakeReviewForm
            caseId={caseId}
            caseStatus={caseData.status}
            result={result}
            canWrite={canWrite}
            onReviewed={refreshEverything}
          />
          {/* Sem recomendação pendente não há o que aprovar acima — este é o
              único caminho para o caso sair da abertura. */}
          <AdvanceStageAction
            caseId={caseId}
            caseData={caseData}
            hasIntake={intake !== null}
            canWrite={canWrite}
            onAdvanced={refreshEverything}
          />
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold text-slate-900">Histórico de decisões</h2>
        <p className="mt-1 text-sm text-slate-500">
          Últimas ações registradas neste caso — o histórico completo fica na aba Histórico.
        </p>
        <div className="mt-3">
          <AuditLogTimeline key={historyVersion} caseId={caseId} limit={5} />
        </div>
      </section>
    </div>
  );
}
