"use client";

import Link from "next/link";

import { EmptyState } from "@/components/ui/EmptyState";
import { stageFor, type CaseStage } from "@/lib/caseStages";
import type { ModuleName } from "@/types/api";

interface CaseStageLockedNoticeProps {
  /** Etapa que o advogado tentou abrir (por URL direta, histórico do navegador ou link antigo). */
  lockedStage: CaseStage;
  currentModule: ModuleName;
  basePath: string;
}

/**
 * Estado de etapa bloqueada. A linha do tempo já não linka etapas futuras,
 * mas a URL continua acessível (link salvo, botão voltar, digitação) — aqui a
 * interface diz por que a etapa está fechada e devolve o advogado para onde a
 * ação existe, em vez de mostrar uma tela vazia sem explicação.
 *
 * É orientação de navegação, não autorização: quem controla a etapa do caso é
 * o backend (CLAUDE.md, seção 16).
 */
export function CaseStageLockedNotice({
  lockedStage,
  currentModule,
  basePath,
}: CaseStageLockedNoticeProps) {
  const currentStage = stageFor(currentModule);

  return (
    <EmptyState
      title={`${lockedStage.label} ainda não foi liberada`}
      description={`Este caso está na etapa ${currentStage.label}. Conclua a etapa atual para o backend liberar ${lockedStage.label} — a interface não avança etapa por conta própria.`}
      action={
        <Link
          href={`${basePath}/${currentStage.segment}`}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          Ir para {currentStage.label}
        </Link>
      }
    />
  );
}
