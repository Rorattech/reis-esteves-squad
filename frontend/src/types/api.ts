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

/** Espelha CaseResponse (backend/app/models/schemas/case.py). */
export interface Case {
  id: string;
  tenant_id: string;
  user_id: string;
  platform: string;
  fraud_type: FraudType;
  urgency: UrgencyLevel;
  status: CaseStatus;
  created_at: string;
  updated_at: string;
}

/** Espelha CaseCreate (backend/app/models/schemas/case.py). */
export interface CaseCreateInput {
  platform: string;
  fraud_type: FraudType;
  urgency?: UrgencyLevel;
}
