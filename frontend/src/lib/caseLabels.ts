import type { FraudType, UrgencyLevel } from "@/types/api";

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
