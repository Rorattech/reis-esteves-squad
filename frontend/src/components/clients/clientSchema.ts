import { z } from "zod";

import { isValidCnpj, isValidCpf, isValidState, isValidZipCode, stripNonDigits } from "@/lib/documents";
import type { ClientCreateInput } from "@/types/api";

/** Campo opcional de texto: string vazia do formulário vira `undefined`. */
const optionalText = (max: number) =>
  z.string().trim().max(max, `Máximo de ${max} caracteres.`).optional().or(z.literal(""));

/**
 * Espelha ClientCreate (backend/app/models/schemas/client.py).
 *
 * A validação de documento aqui é conveniência — o servidor revalida tudo
 * (CLAUDE.md, seção 16). O que ela evita é o advogado preencher a
 * qualificação inteira e descobrir o CPF errado só no submit.
 */
export const clientSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(1, "Informe o nome do cliente.")
      .max(255, "Máximo de 255 caracteres."),
    person_type: z.enum(["individual", "company"]),
    document_number: optionalText(32),
    email: z.string().trim().email("E-mail inválido.").optional().or(z.literal("")),
    phone: optionalText(32),

    rg: optionalText(32),
    rg_issuer: optionalText(32),
    birth_date: z.string().optional().or(z.literal("")),
    nationality: optionalText(60),
    marital_status: z
      .enum(["single", "married", "divorced", "widowed", "separated", "stable_union"])
      .optional()
      .or(z.literal("")),
    profession: optionalText(120),

    address_street: optionalText(255),
    address_number: optionalText(20),
    address_complement: optionalText(120),
    address_district: optionalText(120),
    address_city: optionalText(120),
    address_state: optionalText(2),
    address_zip_code: optionalText(16),
  })
  .superRefine((values, ctx) => {
    if (values.document_number) {
      const isCompany = values.person_type === "company";
      const valid = isCompany
        ? isValidCnpj(values.document_number)
        : isValidCpf(values.document_number);
      if (!valid) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["document_number"],
          message: isCompany ? "CNPJ inválido — confira os dígitos." : "CPF inválido — confira os dígitos.",
        });
      }
    }
    if (values.address_zip_code && !isValidZipCode(values.address_zip_code)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["address_zip_code"],
        message: "CEP inválido — informe 8 dígitos (ex.: 01310-100).",
      });
    }
    if (values.address_state && !isValidState(values.address_state)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["address_state"],
        message: "UF inválida — use a sigla de duas letras (ex.: SP).",
      });
    }
  });

export type ClientFormValues = z.infer<typeof clientSchema>;

/**
 * Converte os valores do formulário no payload da API.
 *
 * Campos em branco são omitidos, não enviados como "": o backend trata `""`
 * como ausência só em alguns campos, e mandar string vazia num enum daria 422.
 * Documento e CEP vão só com dígitos, como o backend armazena.
 */
export function toClientPayload(values: ClientFormValues): ClientCreateInput {
  const payload: ClientCreateInput = {
    full_name: values.full_name,
    person_type: values.person_type,
  };

  if (values.document_number) payload.document_number = stripNonDigits(values.document_number);
  if (values.address_zip_code) payload.address_zip_code = stripNonDigits(values.address_zip_code);
  if (values.address_state) payload.address_state = values.address_state.toUpperCase();
  if (values.marital_status) payload.marital_status = values.marital_status;

  const plainFields = [
    "email",
    "phone",
    "rg",
    "rg_issuer",
    "birth_date",
    "nationality",
    "profession",
    "address_street",
    "address_number",
    "address_complement",
    "address_district",
    "address_city",
  ] as const;

  for (const field of plainFields) {
    const value = values[field];
    if (value) payload[field] = value;
  }

  return payload;
}
