"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { CaseDocumentChecklist } from "@/components/cases/CaseDocumentChecklist";
import { EvidenceAnalysisPanel } from "@/components/evidence/EvidenceAnalysisPanel";
import { EvidenceInventoryTable } from "@/components/evidence/EvidenceInventoryTable";
import { EvidenceUpload } from "@/components/evidence/EvidenceUpload";
import { AccessDeniedState } from "@/components/ui/AccessDeniedState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useAuth } from "@/hooks/useAuth";
import { useCase } from "@/hooks/useCase";
import { useEvidenceAnalysis } from "@/hooks/useEvidenceAnalysis";
import { useEvidenceList } from "@/hooks/useEvidenceList";
import { canWriteCase } from "@/lib/roles";

/**
 * Central de Evidências (roadmap 3.4): pasta probatória do caso — upload com
 * status real de processamento, inventário, pendências documentais e o
 * inventário probatório dos agentes com decisão humana obrigatória. O
 * frontend nunca calcula integridade nem aprova nada sozinho: tudo vem do
 * backend e toda decisão exige ação explícita do advogado (CLAUDE.md,
 * seção 16).
 */
export default function CaseEvidenciasPage() {
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
    evidence,
    isLoading: evidenceLoading,
    error: evidenceError,
    accessDenied,
    reload: reloadEvidence,
  } = useEvidenceList(caseId);
  const {
    analysis,
    isLoading: analysisLoading,
    error: analysisError,
    notRunYet,
    reload: reloadAnalysis,
  } = useEvidenceAnalysis(caseId);

  const [checklistVersion, setChecklistVersion] = useState(0);

  function refreshEverything() {
    reloadCase();
    reloadEvidence();
    reloadAnalysis();
    setChecklistVersion((version) => version + 1);
  }

  if (caseLoading || evidenceLoading) {
    return <LoadingState label="Carregando evidências..." />;
  }
  if (notFound || accessDenied) return <AccessDeniedState />;
  if (caseError) return <ErrorState message={caseError} onRetry={reloadCase} />;
  if (evidenceError) return <ErrorState message={evidenceError} onRetry={reloadEvidence} />;
  if (!caseData) return null;

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-base font-semibold text-slate-900">Enviar evidências</h2>
        <p className="mt-1 text-sm text-slate-500">
          Prints, comprovantes, PDFs e conversas exportadas. Originais preservados intactos, com
          hash de integridade e acesso sempre autenticado.
        </p>
        <div className="mt-3">
          <EvidenceUpload caseId={caseId} canWrite={canWrite} onUploaded={refreshEverything} />
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold text-slate-900">Inventário de arquivos</h2>
        <p className="mt-1 text-sm text-slate-500">
          Status de processamento em tempo real: recebido, processando, processado ou falhou. OCR e
          transcrição geram conteúdo derivado — nunca substituem o original.
        </p>
        <div className="mt-3">
          <EvidenceInventoryTable
            caseId={caseId}
            evidence={evidence}
            canWrite={canWrite}
            onChanged={refreshEverything}
          />
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold text-slate-900">Pendências documentais</h2>
        <p className="mt-1 text-sm text-slate-500">
          O que já chegou, o que falta e o que foi dispensado — alimentado pela triagem, pela
          análise de evidências e pela revisão humana.
        </p>
        <div className="mt-3">
          <CaseDocumentChecklist
            key={checklistVersion}
            caseId={caseId}
            canWrite={canWrite}
            suggestedFromTriage={analysis?.documents_requested ?? []}
          />
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold text-slate-900">Inventário probatório</h2>
        <p className="mt-1 text-sm text-slate-500">
          Achados dos agentes documental e especialista — fatos, inferências e lacunas, cada um
          rastreável à evidência de origem. Sempre recomendação, nunca decisão.
        </p>
        <div className="mt-3">
          <EvidenceAnalysisPanel
            caseId={caseId}
            analysis={analysis}
            isLoading={analysisLoading}
            error={analysisError}
            notRunYet={notRunYet}
            canWrite={canWrite}
            hasEvidence={evidence.length > 0}
            onRetry={reloadAnalysis}
            onChanged={refreshEverything}
          />
        </div>
      </section>
    </div>
  );
}
