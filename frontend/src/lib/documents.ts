/**
 * Validação e formatação de documentos brasileiros — espelha
 * backend/app/core/documents.py.
 *
 * A validação aqui é conveniência de UX: avisa o advogado antes de gastar uma
 * request. A validação que vale é sempre a do servidor (CLAUDE.md, seção 16).
 *
 * O backend guarda e devolve **apenas dígitos**; a máscara é responsabilidade
 * da interface — por isso `formatCpf`/`formatCnpj`/`formatZipCode` existem só
 * para exibição, e o que se envia é sempre `stripNonDigits(...)`.
 */

export const CPF_LENGTH = 11;
export const CNPJ_LENGTH = 14;
export const ZIP_CODE_LENGTH = 8;

const CNPJ_FIRST_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_SECOND_WEIGHTS = [6, ...CNPJ_FIRST_WEIGHTS];

export function stripNonDigits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Dígito verificador pelo módulo 11, usado por CPF e CNPJ. */
function checkDigit(digits: string, weights: number[]): number {
  const total = weights.reduce((sum, weight, index) => sum + Number(digits[index]) * weight, 0);
  const remainder = total % 11;
  return remainder < 2 ? 0 : 11 - remainder;
}

export function isValidCpf(value: string): boolean {
  const digits = stripNonDigits(value);
  // Sequências repetidas ("111.111.111-11") passam no módulo 11 mas não são CPFs.
  if (digits.length !== CPF_LENGTH || new Set(digits).size === 1) return false;

  const first = checkDigit(digits.slice(0, 9), [10, 9, 8, 7, 6, 5, 4, 3, 2]);
  const second = checkDigit(digits.slice(0, 10), [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]);
  return digits.slice(9) === `${first}${second}`;
}

export function isValidCnpj(value: string): boolean {
  const digits = stripNonDigits(value);
  if (digits.length !== CNPJ_LENGTH || new Set(digits).size === 1) return false;

  const first = checkDigit(digits.slice(0, 12), CNPJ_FIRST_WEIGHTS);
  const second = checkDigit(digits.slice(0, 13), CNPJ_SECOND_WEIGHTS);
  return digits.slice(12) === `${first}${second}`;
}

export function isValidZipCode(value: string): boolean {
  return stripNonDigits(value).length === ZIP_CODE_LENGTH;
}

export function formatCpf(value: string): string {
  const digits = stripNonDigits(value).slice(0, CPF_LENGTH);
  if (digits.length !== CPF_LENGTH) return digits;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

export function formatCnpj(value: string): string {
  const digits = stripNonDigits(value).slice(0, CNPJ_LENGTH);
  if (digits.length !== CNPJ_LENGTH) return digits;
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(
    8,
    12,
  )}-${digits.slice(12)}`;
}

/** Formata CPF ou CNPJ conforme o comprimento — para exibir o que veio do backend. */
export function formatDocument(value: string | null | undefined): string {
  if (!value) return "—";
  const digits = stripNonDigits(value);
  if (digits.length === CPF_LENGTH) return formatCpf(digits);
  if (digits.length === CNPJ_LENGTH) return formatCnpj(digits);
  return value;
}

export function formatZipCode(value: string | null | undefined): string {
  if (!value) return "—";
  const digits = stripNonDigits(value);
  if (digits.length !== ZIP_CODE_LENGTH) return value;
  return `${digits.slice(0, 5)}-${digits.slice(5)}`;
}

/** Siglas de UF aceitas — espelha _BRAZILIAN_STATES do schema do backend. */
export const BRAZILIAN_STATES = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
  "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
] as const;

export function isValidState(value: string): boolean {
  return (BRAZILIAN_STATES as readonly string[]).includes(value.trim().toUpperCase());
}
