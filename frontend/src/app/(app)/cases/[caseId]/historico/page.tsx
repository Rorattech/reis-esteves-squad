"use client";

import { useParams } from "next/navigation";

import { AuditLogTimeline } from "@/components/cases/AuditLogTimeline";

export default function CaseHistoricoPage() {
  const params = useParams<{ caseId: string }>();
  return <AuditLogTimeline caseId={params.caseId} />;
}
