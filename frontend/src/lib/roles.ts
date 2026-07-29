import type { User, UserRole } from "@/types/api";

/**
 * Papéis que o backend autoriza a criar/editar casos, relatos, checklist e
 * revisão humana (CLAUDE.md, seção 12) — `viewer` só lê. Mesmo conjunto de
 * papéis usado em `_require_case_writer` em todas as rotas de
 * `backend/app/api/v1/{cases,intake}.py`.
 *
 * Esconder uma ação para quem não pode usá-la é só uma conveniência de UX —
 * a autorização real é sempre reforçada pelo backend (CLAUDE.md, seção 16).
 */
const CASE_WRITER_ROLES = new Set<UserRole>(["admin", "lawyer", "paralegal"]);

export function canWriteCase(user: User | null): boolean {
  return user !== null && CASE_WRITER_ROLES.has(user.role);
}
