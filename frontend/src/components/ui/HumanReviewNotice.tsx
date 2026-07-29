/**
 * Aviso fixo de revisão humana obrigatória (CLAUDE.md, seção 16). Deve
 * aparecer em toda tela que exiba output gerado por IA.
 */
export function HumanReviewNotice() {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="mt-0.5 h-4 w-4 flex-shrink-0"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.63-1.516 2.63H3.72c-1.346 0-2.189-1.463-1.515-2.63L8.485 2.495ZM10 6a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 6Zm0 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clipRule="evenodd"
        />
      </svg>
      <p>
        <span className="font-semibold">Revisão humana obrigatória.</span> Todo conteúdo gerado
        por IA neste caso é um rascunho e exige aprovação explícita de um advogado antes de
        qualquer uso.
      </p>
    </div>
  );
}
