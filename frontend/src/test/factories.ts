/**
 * Fábricas de objetos de domínio para os testes.
 *
 * Existem porque `makeCase` estava duplicado em sete arquivos de teste: cada
 * campo novo em `Case` obrigava a editar os sete, e um esquecido só aparecia
 * como erro de tipo no arquivo errado. Importe daqui em vez de recriar.
 */

import type { Case, Client, ClientSummary, FraudModality, Platform } from "@/types/api";

export function makePlatform(overrides: Partial<Platform> = {}): Platform {
  return {
    id: "platform-1",
    slug: "whatsapp",
    label: "WhatsApp",
    is_system: true,
    active: true,
    sort_order: 10,
    created_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

export function makeFraudModality(overrides: Partial<FraudModality> = {}): FraudModality {
  return {
    id: "modality-1",
    slug: "pix",
    label: "Golpe do PIX",
    family: "pix",
    is_system: true,
    active: true,
    sort_order: 10,
    created_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

export function makeClientSummary(overrides: Partial<ClientSummary> = {}): ClientSummary {
  return {
    id: "client-1",
    code: "CLI-000001",
    full_name: "Maria Souza de Oliveira",
    ...overrides,
  };
}

export function makeClient(overrides: Partial<Client> = {}): Client {
  return {
    id: "client-1",
    tenant_id: "tenant-1",
    code: "CLI-000001",
    full_name: "Maria Souza de Oliveira",
    person_type: "individual",
    document_number: "52998224725",
    email: "maria@example.com.br",
    phone: "11987654321",
    rg: "12.345.678-9",
    rg_issuer: "SSP/SP",
    birth_date: "1985-03-14",
    nationality: "brasileira",
    marital_status: "married",
    profession: "professora",
    address_street: "Rua das Acácias",
    address_number: "220",
    address_complement: "apto 51",
    address_district: "Vila Mariana",
    address_city: "São Paulo",
    address_state: "SP",
    address_zip_code: "01310100",
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}

export function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "tenant-1",
    user_id: "user-1",
    code: "CAS-2026-000001",
    client_id: null,
    client: null,
    area: null,
    matter: null,
    platform: "WhatsApp",
    platform_entry: makePlatform(),
    fraud_type: "pix",
    fraud_modality: makeFraudModality(),
    urgency: "high",
    status: "in_progress",
    current_module: "intake",
    human_review_required: true,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-02T10:00:00Z",
    ...overrides,
  };
}
