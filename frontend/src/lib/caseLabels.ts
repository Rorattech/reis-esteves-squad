import type {
  AuditActor,
  CaseArea,
  CaseStatus,
  DocumentChecklistStatus,
  EvidenceProcessingStatus,
  FraudType,
  IntakeOutcome,
  UrgencyLevel,
} from "@/types/api";

export const FRAUD_TYPE_LABELS: Record<FraudType, string> = {
  pix: "Golpe PIX",
  marketplace: "Marketplace",
  fake_profile: "Perfil falso",
  fake_lawyer: "Falso advogado",
  other: "Outro",
};

export const URGENCY_LABELS: Record<UrgencyLevel, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  critical: "Crítica",
};

export const CASE_AREA_LABELS: Record<CaseArea, string> = {
  civil: "Cível",
  family: "Família",
  criminal: "Penal",
  labor: "Trabalhista",
  consumer: "Consumidor",
  digital: "Digital",
};

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  draft: "Rascunho",
  in_progress: "Em andamento",
  pending_approval: "Aguardando aprovação",
  approved: "Aprovado",
  completed: "Concluído",
  archived: "Arquivado",
};

export const DOCUMENT_STATUS_LABELS: Record<DocumentChecklistStatus, string> = {
  received: "Recebido",
  pending: "Pendente",
  waived: "Dispensado",
};

/** Espelha orchestrator.state.IntakeOutcome (Fase 2.3) — nunca um estado final do caso. */
export const INTAKE_OUTCOME_LABELS: Record<IntakeOutcome, string> = {
  completed: "Classificação preliminar concluída",
  blocked: "Fora do escopo do Squad Digital",
  awaiting_information: "Aguardando mais informações",
  awaiting_human_review: "Aguardando revisão humana",
};

/** Espelha EvidenceProcessingStatus (backend/app/models/enums.py) — Fase 3. */
export const EVIDENCE_STATUS_LABELS: Record<EvidenceProcessingStatus, string> = {
  received: "Recebido",
  processing: "Processando",
  processed: "Processado",
  failed: "Falhou",
};

/** Natureza de um achado probatório (roadmap 3.3 — fato × inferência × lacuna). */
export const FINDING_CATEGORY_LABELS: Record<"fact" | "inference" | "missing_info", string> = {
  fact: "Fato extraído",
  inference: "Inferência técnica",
  missing_info: "Informação pendente",
};

export const FINDING_RELEVANCE_LABELS: Record<"low" | "medium" | "high", string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
};

export const AUDIT_ACTOR_LABELS: Record<AuditActor, string> = {
  system: "Sistema",
  agent: "Agente de IA",
  human: "Advogado(a)",
};
