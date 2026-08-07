import Link from "next/link";

interface AccessDeniedStateProps {
  /** Mensagem específica, se houver — cai para um texto neutro por padrão. */
  message?: string;
  /** Destino do botão de saída. Padrão: a lista de casos. */
  backHref?: string;
  backLabel?: string;
}

/**
 * Estado para um recurso que não existe ou não pertence ao tenant do usuário
 * autenticado. O backend devolve 404 (nunca 403) para os dois casos, de
 * propósito — não confirma nem nega a existência do recurso para quem não é
 * dono (CLAUDE.md, seção 7). Esta tela espelha essa ambiguidade: nunca diz
 * "esse caso existe mas não é seu", só que o acesso não é possível.
 */
export function AccessDeniedState({
  message,
  backHref = "/cases",
  backLabel = "Voltar para Casos",
}: AccessDeniedStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-slate-300 bg-slate-50 px-6 py-16 text-center">
      <p className="text-sm font-medium text-slate-800">
        {message ?? "Este caso não existe ou você não tem acesso a ele."}
      </p>
      <Link
        href={backHref}
        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
      >
        {backLabel}
      </Link>
    </div>
  );
}
