/**
 * Tipos espelhando os schemas Pydantic do backend (backend/app/models/schemas/).
 * Nunca redefina esses formatos "de cabeça" em outro lugar do frontend.
 */

export type UserRole = "admin" | "lawyer" | "paralegal" | "viewer";

export type FraudType = "pix" | "marketplace" | "fake_profile" | "fake_lawyer" | "other";

export type UrgencyLevel = "low" | "medium" | "high" | "critical";

export type CaseStatus =
  | "draft"
  | "in_progress"
  | "pending_approval"
  | "approved"
  | "completed"
  | "archived";

/** Espelha CaseArea (backend/app/models/enums.py). */
export type CaseArea = "civil" | "family" | "criminal" | "labor" | "consumer" | "digital";

/**
 * Espelha ModuleName (backend/app/models/enums.py) — um dos 6 módulos do
 * workflow, nesta ordem fixa (orchestrator/router.py::MODULE_ORDER). Usado
 * para saber qual etapa da linha do tempo do caso está liberada.
 */
export type ModuleName = "intake" | "evidence" | "research" | "strategy" | "drafting" | "review";

/** Espelha UserResponse (backend/app/models/schemas/auth.py). */
export interface User {
  id: string;
  tenant_id: string;
  tenant_name: string;
  email: string;
  role: UserRole;
  created_at: string;
}

/** Espelha TokenResponse (backend/app/models/schemas/auth.py). */
export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

/** Espelha PersonType (backend/app/models/enums.py). */
export type PersonType = "individual" | "company";

/** Espelha MaritalStatus (backend/app/models/enums.py). */
export type MaritalStatus =
  | "single"
  | "married"
  | "divorced"
  | "widowed"
  | "separated"
  | "stable_union";

/** Espelha PlatformResponse (backend/app/models/schemas/catalog.py). */
export interface Platform {
  id: string;
  slug: string;
  label: string;
  is_system: boolean;
  active: boolean;
  sort_order: number;
  created_at: string;
}

/**
 * Espelha FraudModalityResponse (backend/app/models/schemas/catalog.py).
 * `family` é a família de FraudType a que a modalidade pertence — é o que o
 * grafo e os prompts leem (ver backend/app/models/catalog.py).
 */
export interface FraudModality {
  id: string;
  slug: string;
  label: string;
  family: FraudType;
  is_system: boolean;
  active: boolean;
  sort_order: number;
  created_at: string;
}

/** Espelha PlatformCreate (backend/app/models/schemas/catalog.py). */
export interface PlatformCreateInput {
  label: string;
}

/** Espelha FraudModalityCreate — `family` é obrigatório. */
export interface FraudModalityCreateInput {
  label: string;
  family: FraudType;
}

/**
 * Espelha ClientSummary (backend/app/models/schemas/client.py) — o cliente
 * como aparece dentro de um caso. **Sem documento de propósito**: CPF completo
 * só em `GET /clients/{id}`.
 */
export interface ClientSummary {
  id: string;
  code: string;
  full_name: string;
}

/** Espelha ClientResponse (backend/app/models/schemas/client.py). */
export interface Client {
  id: string;
  tenant_id: string;
  code: string;
  full_name: string;
  person_type: PersonType;
  document_number: string | null;
  email: string | null;
  phone: string | null;
  rg: string | null;
  rg_issuer: string | null;
  birth_date: string | null;
  nationality: string | null;
  marital_status: MaritalStatus | null;
  profession: string | null;
  address_street: string | null;
  address_number: string | null;
  address_complement: string | null;
  address_district: string | null;
  address_city: string | null;
  address_state: string | null;
  address_zip_code: string | null;
  created_at: string;
  updated_at: string;
}

/** Espelha ClientCreate (backend/app/models/schemas/client.py). */
export interface ClientCreateInput {
  full_name: string;
  person_type?: PersonType;
  document_number?: string | null;
  email?: string | null;
  phone?: string | null;
  rg?: string | null;
  rg_issuer?: string | null;
  birth_date?: string | null;
  nationality?: string | null;
  marital_status?: MaritalStatus | null;
  profession?: string | null;
  address_street?: string | null;
  address_number?: string | null;
  address_complement?: string | null;
  address_district?: string | null;
  address_city?: string | null;
  address_state?: string | null;
  address_zip_code?: string | null;
}

/** Espelha ClientUpdate — todos os campos são opcionais (semântica PATCH). */
export type ClientUpdateInput = Partial<ClientCreateInput>;

/**
 * Espelha CaseResponse (backend/app/models/schemas/case.py).
 * `code` é o identificador legível do caso — é ele que a interface exibe; o
 * `id` (UUID) fica só na URL. `platform` e `fraud_type` são rótulo e família
 * denormalizados da entrada de catálogo escolhida.
 */
export interface Case {
  id: string;
  tenant_id: string;
  user_id: string;
  code: string;
  client_id: string | null;
  client: ClientSummary | null;
  area: CaseArea | null;
  matter: string | null;
  platform: string;
  platform_entry: Platform;
  fraud_type: FraudType;
  fraud_modality: FraudModality;
  urgency: UrgencyLevel;
  status: CaseStatus;
  current_module: ModuleName;
  human_review_required: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Espelha CaseCreate (backend/app/models/schemas/case.py). client_id, area e
 * matter são opcionais: podem não ser conhecidos na abertura e serem
 * preenchidos depois, pela triagem ou por correção humana na tela de edição
 * do caso.
 */
export interface CaseCreateInput {
  platform_id: string;
  fraud_modality_id: string;
  urgency?: UrgencyLevel;
  /** Cliente já cadastrado. Mutuamente exclusivo com `client`. */
  client_id?: string;
  /** Cliente novo, criado na mesma transação do caso. Exclusivo com `client_id`. */
  client?: ClientCreateInput;
  area?: CaseArea;
  matter?: string;
}

/** Espelha CaseUpdate (backend/app/models/schemas/case.py) — todos os campos são opcionais. */
export interface CaseUpdateInput {
  platform_id?: string;
  fraud_modality_id?: string;
  urgency?: UrgencyLevel;
  status?: CaseStatus;
  client_id?: string | null;
  area?: CaseArea;
  matter?: string;
  current_module?: ModuleName;
  human_review_required?: boolean;
}

/**
 * Espelha CaseIntakeResponse (backend/app/models/schemas/case_intake.py).
 * `estimated_loss_amount` chega como string — o backend serializa `Decimal`
 * como string no JSON para não perder precisão (nunca `number`).
 */
export interface CaseIntake {
  id: string;
  tenant_id: string;
  case_id: string;
  submitted_by: string;
  narrative: string;
  estimated_loss_amount: string | null;
  incident_date: string | null;
  has_police_report: boolean | null;
  claimed_documents: string[];
  pending_information: string[];
  created_at: string;
  updated_at: string;
}

/** Espelha CaseIntakeCreate (backend/app/models/schemas/case_intake.py). */
export interface CaseIntakeCreateInput {
  narrative: string;
  estimated_loss_amount?: number | null;
  incident_date?: string | null;
  has_police_report?: boolean | null;
  claimed_documents?: string[];
  pending_information?: string[];
}

/** Espelha CaseIntakeUpdate (backend/app/models/schemas/case_intake.py). */
export type CaseIntakeUpdateInput = Partial<CaseIntakeCreateInput>;

/** Espelha DocumentChecklistStatus (backend/app/models/enums.py). */
export type DocumentChecklistStatus = "received" | "pending" | "waived";

/** Espelha CaseDocumentResponse (backend/app/models/schemas/case_document.py). */
export interface CaseDocument {
  id: string;
  tenant_id: string;
  case_id: string;
  name: string;
  status: DocumentChecklistStatus;
  origin: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** Espelha CaseDocumentCreate (backend/app/models/schemas/case_document.py). */
export interface CaseDocumentCreateInput {
  name: string;
  status?: DocumentChecklistStatus;
  origin?: string;
  notes?: string | null;
}

/** Espelha CaseDocumentUpdate (backend/app/models/schemas/case_document.py). */
export interface CaseDocumentUpdateInput {
  status?: DocumentChecklistStatus;
  notes?: string | null;
}

/**
 * Espelha IntakeOutcomeSchema (backend/app/models/schemas/intake.py), que
 * por sua vez espelha orchestrator.state.IntakeOutcome (Fase 2.3).
 */
export type IntakeOutcome = "completed" | "blocked" | "awaiting_information" | "awaiting_human_review";

/**
 * Espelha IntakeResultResponse (backend/app/models/schemas/intake.py) — o
 * resultado mais recente de coordinator+triage. Nunca uma decisão final:
 * `human_review_required` indica se ainda depende de aprovação humana.
 */
export interface IntakeResult {
  case_id: string;
  intake_outcome: IntakeOutcome | null;
  platform: string;
  fraud_type: FraudType;
  urgency: UrgencyLevel;
  area: CaseArea | null;
  matter: string | null;
  documents_requested: string[];
  missing_information: string[];
  out_of_scope_reason: string | null;
  human_review_required: boolean;
  status: CaseStatus;
  current_module: ModuleName;
}

/**
 * Espelha CaseStageAdvanceRequest (backend/app/models/schemas/intake.py) —
 * decisão humana de concluir a abertura do caso e avançar para Evidências
 * quando não há recomendação de triagem a revisar.
 */
export interface CaseStageAdvanceInput {
  notes?: string | null;
}

/** Espelha IntakeReviewDecision (backend/app/models/schemas/intake.py). */
export type IntakeReviewDecision = "approve" | "correct" | "return_for_information";

/**
 * Espelha IntakeReviewRequest (backend/app/models/schemas/intake.py).
 * `notes` é obrigatório para qualquer decisão que não seja "approve" — o
 * backend rejeita a requisição (422) sem isso; o frontend replica a mesma
 * regra antes de enviar (ver IntakeReviewForm).
 */
export interface IntakeReviewInput {
  decision: IntakeReviewDecision;
  notes?: string | null;
  platform_id?: string;
  fraud_modality_id?: string;
  urgency?: UrgencyLevel;
  area?: CaseArea;
  matter?: string;
}

/** Espelha EvidenceProcessingStatus (backend/app/models/enums.py) — Fase 3. */
export type EvidenceProcessingStatus = "received" | "processing" | "processed" | "failed";

/** Espelha EvidenceFileResponse (backend/app/models/schemas/evidence_file.py). */
export interface EvidenceFile {
  id: string;
  tenant_id: string;
  case_id: string;
  uploaded_by: string;
  original_filename: string;
  mime_type: string;
  extension: string;
  size_bytes: number;
  sha256_hash: string;
  origin: string;
  status: EvidenceProcessingStatus;
  duplicate_of_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  is_duplicate: boolean;
}

/** Espelha ExtractionOutcome (backend/app/models/enums.py). */
export type ExtractionOutcome = "succeeded" | "failed";

/** Espelha ExtractionReviewVerdict (backend/app/models/enums.py). */
export type ExtractionReviewVerdict = "confirmed" | "extraction_error";

/** Espelha ExtractionReviewResponse (backend/app/models/schemas/evidence_extraction.py). */
export interface ExtractionReview {
  id: string;
  extraction_id: string;
  reviewer_id: string;
  verdict: ExtractionReviewVerdict;
  note: string | null;
  created_at: string;
}

/** Espelha ExtractionReviewCreate (backend/app/models/schemas/evidence_extraction.py). */
export interface ExtractionReviewInput {
  verdict: ExtractionReviewVerdict;
  note?: string | null;
}

/**
 * Espelha EvidenceExtractionResponse (backend/app/models/schemas/evidence_extraction.py).
 * `extracted_text` é sempre conteúdo DERIVADO (OCR/decodificação) — a
 * interface nunca o apresenta como prova perfeita; `confidence` e
 * `limitations` devem ser exibidos junto (roadmap 3.2/3.5).
 */
export interface EvidenceExtraction {
  id: string;
  evidence_id: string;
  kind: string;
  outcome: ExtractionOutcome;
  extracted_text: string | null;
  confidence: number | null;
  limitations: string | null;
  tool_name: string;
  tool_version: string;
  input_sha256: string;
  output_sha256: string | null;
  duration_ms: number;
  error_message: string | null;
  created_at: string;
  reviews: ExtractionReview[];
}

/** Espelha EvidenceFindingResponse (backend/app/models/schemas/evidence_analysis.py). */
export interface EvidenceFinding {
  id: string;
  evidence_id: string | null;
  agent: string;
  category: "fact" | "inference" | "missing_info";
  evidence_type: string;
  summary: string;
  relevance: "low" | "medium" | "high";
  suggested_use: string;
  gaps: string[];
  confidence: number;
  status: string;
  created_at: string;
}

/** Espelha SpecialistAssessmentResponse (backend/app/models/schemas/evidence_analysis.py). */
export interface SpecialistAssessment {
  platform_context: string;
  platform_failure: string | null;
  report_mechanism_analysis: string | null;
  preservation_recommendations: string[];
  hypotheses: string[];
  status: string;
}

/** Espelha EvidenceAnalysisResultResponse (backend/app/models/schemas/evidence_analysis.py). */
export interface EvidenceAnalysisResult {
  case_id: string;
  evidence_outcome: "awaiting_human_review" | "awaiting_information" | null;
  findings: EvidenceFinding[];
  specialist_assessment: SpecialistAssessment | null;
  documents_requested: string[];
  human_review_required: boolean;
  status: CaseStatus;
  current_module: ModuleName;
}

/** Espelha EvidenceReviewRequest (backend/app/models/schemas/evidence_analysis.py). */
export interface EvidenceAnalysisReviewInput {
  decision: "approve" | "return_for_information";
  notes?: string | null;
}

/** Espelha AuditActor (backend/app/models/enums.py). */
export type AuditActor = "system" | "agent" | "human";

/** Espelha AuditLogEntryResponse (backend/app/models/schemas/intake.py). */
export interface AuditLogEntry {
  id: string;
  actor: AuditActor;
  actor_id: string;
  action: string;
  module: ModuleName;
  model_used: string;
  tokens_used: number;
  duration_ms: number;
  metadata: Record<string, unknown>;
  created_at: string;
}
