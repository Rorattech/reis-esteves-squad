/**
 * Chamadas de API centralizadas (CLAUDE.md, seção 6). Nenhum componente ou
 * hook deve chamar `fetch` diretamente contra o backend — sempre via `api`.
 */

import {
  clearStoredRefreshToken,
  getStoredRefreshToken,
  useAuthStore,
} from "@/stores/authStore";
import type {
  AuditLogEntry,
  Case,
  CaseCreateInput,
  Client,
  ClientCreateInput,
  ClientUpdateInput,
  FraudModality,
  FraudModalityCreateInput,
  Platform,
  PlatformCreateInput,
  CaseDocument,
  CaseDocumentCreateInput,
  CaseDocumentUpdateInput,
  CaseIntake,
  CaseIntakeCreateInput,
  CaseIntakeUpdateInput,
  CaseStatus,
  CaseStageAdvanceInput,
  CaseUpdateInput,
  EvidenceAnalysisResult,
  EvidenceAnalysisReviewInput,
  EvidenceExtraction,
  EvidenceFile,
  ExtractionReview,
  ExtractionReviewInput,
  IntakeResult,
  IntakeReviewInput,
  TokenResponse,
  User,
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ");
    }
  } catch {
    // corpo da resposta não é JSON — segue com a mensagem genérica abaixo.
  }
  return `Erro inesperado (HTTP ${response.status}).`;
}

/**
 * Renova o access token a partir do refresh token guardado localmente.
 *
 * Usado tanto na restauração de sessão ao carregar a página quanto no retry
 * automático de uma request que voltou 401 (ver `request` abaixo). Só uma
 * chamada de refresh corre por vez — `inflightRefresh` deduplica retries
 * concorrentes (ex.: várias requests em paralelo recebendo 401 juntas).
 */
let inflightRefresh: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clearStoredRefreshToken();
    return null;
  }
  const tokens: TokenResponse = await response.json();
  useAuthStore.getState().setAccessToken(tokens.access_token);
  return tokens.access_token;
}

function refreshAccessTokenOnce(): Promise<string | null> {
  if (!inflightRefresh) {
    inflightRefresh = refreshAccessToken().finally(() => {
      inflightRefresh = null;
    });
  }
  return inflightRefresh;
}

async function rawRequest(
  path: string,
  options: RequestInit = {},
  { allowRefreshRetry = true }: { allowRefreshRetry?: boolean } = {},
): Promise<Response> {
  const accessToken = useAuthStore.getState().accessToken;
  // FormData define o próprio Content-Type (multipart + boundary) — forçar
  // application/json quebraria o upload de evidências.
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

  if (response.status === 401 && allowRefreshRetry) {
    const newAccessToken = await refreshAccessTokenOnce();
    if (newAccessToken) {
      return rawRequest(path, options, { allowRefreshRetry: false });
    }
    useAuthStore.getState().clear();
    throw new ApiError(401, "Sessão expirada. Faça login novamente.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }
  return response;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retryOptions: { allowRefreshRetry?: boolean } = {},
): Promise<T> {
  const response = await rawRequest(path, options, retryOptions);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  async login(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { allowRefreshRetry: false },
    );
  },

  /** Restaura a sessão a partir do refresh token salvo (ex.: ao recarregar a página). */
  restoreSession: refreshAccessToken,

  async getMe(): Promise<User> {
    return request<User>("/auth/me");
  },

  /**
   * Busca e filtro vão para o servidor porque a busca inclui o nome do
   * cliente: filtrar no navegador exigiria baixar a base de casos inteira,
   * com os nomes, para toda sessão aberta.
   *
   * POST apesar de ser leitura: o termo casa com o nome do cliente, e query
   * string vaza para access log, histórico do navegador, cabeçalho Referer e
   * cache de proxy (CLAUDE.md, seção 12).
   */
  async listCases(params: { search?: string; status?: CaseStatus } = {}): Promise<Case[]> {
    return request<Case[]>("/cases/search", {
      method: "POST",
      body: JSON.stringify({
        search: params.search?.trim() || null,
        status: params.status ?? null,
      }),
    });
  },

  /**
   * Busca por nome, CPF/CNPJ (com ou sem máscara) ou código do cliente.
   * POST pelo mesmo motivo de `listCases` — o termo pode ser um CPF.
   */
  async listClients(search?: string): Promise<Client[]> {
    return request<Client[]>("/clients/search", {
      method: "POST",
      body: JSON.stringify({ search: search?.trim() || null }),
    });
  },

  async getClient(clientId: string): Promise<Client> {
    return request<Client>(`/clients/${clientId}`);
  },

  async createClient(input: ClientCreateInput): Promise<Client> {
    return request<Client>("/clients", { method: "POST", body: JSON.stringify(input) });
  },

  async updateClient(clientId: string, input: ClientUpdateInput): Promise<Client> {
    return request<Client>(`/clients/${clientId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  async listPlatforms(): Promise<Platform[]> {
    return request<Platform[]>("/catalog/platforms");
  },

  /** Cadastra uma plataforma própria do escritório (opção "Outro"). */
  async createPlatform(input: PlatformCreateInput): Promise<Platform> {
    return request<Platform>("/catalog/platforms", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async listFraudModalities(): Promise<FraudModality[]> {
    return request<FraudModality[]>("/catalog/fraud-modalities");
  },

  /** Cadastra uma modalidade própria do escritório — `family` é obrigatório. */
  async createFraudModality(input: FraudModalityCreateInput): Promise<FraudModality> {
    return request<FraudModality>("/catalog/fraud-modalities", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async getCase(caseId: string): Promise<Case> {
    return request<Case>(`/cases/${caseId}`);
  },

  async createCase(input: CaseCreateInput): Promise<Case> {
    return request<Case>("/cases", { method: "POST", body: JSON.stringify(input) });
  },

  async updateCase(caseId: string, input: CaseUpdateInput): Promise<Case> {
    return request<Case>(`/cases/${caseId}`, { method: "PATCH", body: JSON.stringify(input) });
  },

  /** Irreversível: leva junto relato, checklist, evidências e checkpoints do caso. */
  async deleteCase(caseId: string): Promise<void> {
    return request<void>(`/cases/${caseId}`, { method: "DELETE" });
  },

  /** 404 se o caso não existir OU se o relato inicial ainda não tiver sido enviado. */
  async getCaseIntake(caseId: string): Promise<CaseIntake> {
    return request<CaseIntake>(`/cases/${caseId}/intake`);
  },

  /** Idempotente: reenviar substitui o relato anterior (mesmo endpoint para criar e editar). */
  async submitCaseIntake(caseId: string, input: CaseIntakeCreateInput): Promise<CaseIntake> {
    return request<CaseIntake>(`/cases/${caseId}/intake`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async updateCaseIntake(caseId: string, input: CaseIntakeUpdateInput): Promise<CaseIntake> {
    return request<CaseIntake>(`/cases/${caseId}/intake`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  async listCaseDocuments(caseId: string): Promise<CaseDocument[]> {
    return request<CaseDocument[]>(`/cases/${caseId}/documents`);
  },

  async addCaseDocument(caseId: string, input: CaseDocumentCreateInput): Promise<CaseDocument> {
    return request<CaseDocument>(`/cases/${caseId}/documents`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async updateCaseDocument(
    caseId: string,
    documentId: string,
    input: CaseDocumentUpdateInput,
  ): Promise<CaseDocument> {
    return request<CaseDocument>(`/cases/${caseId}/documents/${documentId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  /** Executa coordinator + triage (orchestrator/graphs/intake.py) para o caso. */
  async runIntake(caseId: string): Promise<IntakeResult> {
    return request<IntakeResult>(`/cases/${caseId}/intake/run`, { method: "POST" });
  },

  /** 404 se o caso não existir OU se o Intake ainda não tiver sido executado. */
  async getIntakeResult(caseId: string): Promise<IntakeResult> {
    return request<IntakeResult>(`/cases/${caseId}/intake/result`);
  },

  /** 409 se o caso não tiver nenhuma recomendação pendente de revisão. */
  async reviewIntake(caseId: string, input: IntakeReviewInput): Promise<Case> {
    return request<Case>(`/cases/${caseId}/intake/review`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * Conclui a abertura do caso e o avança para Evidências por decisão humana,
   * sem passar por uma recomendação de triagem. 409 se o caso já tiver saído
   * da abertura; 422 se ainda não houver relato inicial.
   */
  async advanceCaseStage(caseId: string, input: CaseStageAdvanceInput = {}): Promise<Case> {
    return request<Case>(`/cases/${caseId}/intake/advance`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async getAuditLog(caseId: string): Promise<AuditLogEntry[]> {
    return request<AuditLogEntry[]>(`/cases/${caseId}/audit-log`);
  },

  // --- Evidências (Fase 3) ---------------------------------------------------

  async listEvidence(caseId: string): Promise<EvidenceFile[]> {
    return request<EvidenceFile[]>(`/cases/${caseId}/evidence`);
  },

  async getEvidence(caseId: string, evidenceId: string): Promise<EvidenceFile> {
    return request<EvidenceFile>(`/cases/${caseId}/evidence/${evidenceId}`);
  },

  /** Upload multipart — o backend valida MIME, tamanho e conteúdo; o original é preservado intacto. */
  async uploadEvidence(caseId: string, file: File, origin = "upload_portal"): Promise<EvidenceFile> {
    const body = new FormData();
    body.append("file", file);
    body.append("origin", origin);
    return request<EvidenceFile>(`/cases/${caseId}/evidence`, { method: "POST", body });
  },

  /**
   * Baixa o conteúdo original por rota autenticada (nunca existe URL pública
   * permanente para uma evidência — CLAUDE.md, seção 12). Cada acesso gera
   * entrada de auditoria no backend (cadeia de custódia).
   */
  async downloadEvidence(caseId: string, evidenceId: string): Promise<Blob> {
    const response = await rawRequest(`/cases/${caseId}/evidence/${evidenceId}/download`);
    return response.blob();
  },

  /** Dispara (re)processamento da extração — 409 se já estiver em processamento. */
  async processEvidence(caseId: string, evidenceId: string): Promise<EvidenceFile> {
    return request<EvidenceFile>(`/cases/${caseId}/evidence/${evidenceId}/process`, {
      method: "POST",
    });
  },

  async listEvidenceExtractions(
    caseId: string,
    evidenceId: string,
  ): Promise<EvidenceExtraction[]> {
    return request<EvidenceExtraction[]>(`/cases/${caseId}/evidence/${evidenceId}/extractions`);
  },

  /** Revisão humana do texto extraído — cria um registro auditado, nunca substitui o texto. */
  async reviewEvidenceExtraction(
    caseId: string,
    evidenceId: string,
    extractionId: string,
    input: ExtractionReviewInput,
  ): Promise<ExtractionReview> {
    return request<ExtractionReview>(
      `/cases/${caseId}/evidence/${evidenceId}/extractions/${extractionId}/review`,
      { method: "POST", body: JSON.stringify(input) },
    );
  },

  /** Executa documental + specialist (orchestrator/graphs/evidence.py) para o caso. */
  async runEvidenceAnalysis(caseId: string): Promise<EvidenceAnalysisResult> {
    return request<EvidenceAnalysisResult>(`/cases/${caseId}/evidence/analysis/run`, {
      method: "POST",
    });
  },

  /** 404 se o caso não existir OU se a análise ainda não tiver sido executada. */
  async getEvidenceAnalysis(caseId: string): Promise<EvidenceAnalysisResult> {
    return request<EvidenceAnalysisResult>(`/cases/${caseId}/evidence/analysis/result`);
  },

  /** 409 se não houver análise de evidências pendente de revisão. */
  async reviewEvidenceAnalysis(
    caseId: string,
    input: EvidenceAnalysisReviewInput,
  ): Promise<EvidenceAnalysisResult> {
    return request<EvidenceAnalysisResult>(`/cases/${caseId}/evidence/analysis/review`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
