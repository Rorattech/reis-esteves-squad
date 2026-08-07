"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { BRAZILIAN_STATES } from "@/lib/documents";
import { MARITAL_STATUS_LABELS, PERSON_TYPE_LABELS } from "@/lib/caseLabels";
import type { Client, MaritalStatus, PersonType } from "@/types/api";

import { clientSchema, type ClientFormValues } from "./clientSchema";

const PERSON_TYPE_OPTIONS = Object.entries(PERSON_TYPE_LABELS) as [PersonType, string][];
const MARITAL_STATUS_OPTIONS = Object.entries(MARITAL_STATUS_LABELS) as [MaritalStatus, string][];

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none";
const selectClass = `${inputClass} bg-white`;

interface ClientFormProps {
  /** Cliente existente, quando o formulário está editando. */
  client?: Client;
  onSubmit: (values: ClientFormValues) => Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  formError?: string | null;
}

function defaultValues(client?: Client): Partial<ClientFormValues> {
  return {
    full_name: client?.full_name ?? "",
    person_type: client?.person_type ?? "individual",
    document_number: client?.document_number ?? "",
    email: client?.email ?? "",
    phone: client?.phone ?? "",
    rg: client?.rg ?? "",
    rg_issuer: client?.rg_issuer ?? "",
    birth_date: client?.birth_date ?? "",
    nationality: client?.nationality ?? "brasileira",
    marital_status: client?.marital_status ?? "",
    profession: client?.profession ?? "",
    address_street: client?.address_street ?? "",
    address_number: client?.address_number ?? "",
    address_complement: client?.address_complement ?? "",
    address_district: client?.address_district ?? "",
    address_city: client?.address_city ?? "",
    address_state: client?.address_state ?? "",
    address_zip_code: client?.address_zip_code ?? "",
  };
}

/**
 * Formulário de qualificação do cliente.
 *
 * Os campos não são burocracia: são exatamente o que a petição inicial exige
 * (CPC art. 319, II), e o município/UF é o que fixa o foro do consumidor
 * (CDC art. 101, I) — o único dado do cliente que o sistema envia aos agentes
 * de IA.
 */
export function ClientForm({
  client,
  onSubmit,
  onCancel,
  submitLabel = "Cadastrar cliente",
  formError,
}: ClientFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ClientFormValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: defaultValues(client),
  });

  // Estado local em vez de `watch()`: o React Compiler não consegue memoizar
  // as funções que o react-hook-form devolve, e desliga a otimização do
  // componente inteiro quando `watch` aparece. O onChange abaixo mantém os
  // dois em sincronia.
  const [personType, setPersonType] = useState<PersonType>(
    client?.person_type ?? "individual",
  );
  const isCompany = personType === "company";
  const personTypeField = register("person_type");

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
      <fieldset className="space-y-4">
        <legend className="text-sm font-medium text-slate-900">Identificação</legend>

        <div>
          <label htmlFor="person_type" className="block text-sm font-medium text-slate-700">
            Natureza
          </label>
          <select
            id="person_type"
            className={selectClass}
            {...personTypeField}
            onChange={(event) => {
              personTypeField.onChange(event);
              setPersonType(event.target.value as PersonType);
            }}
          >
            {PERSON_TYPE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="full_name" className="block text-sm font-medium text-slate-700">
            {isCompany ? "Razão social" : "Nome completo"}
          </label>
          <input id="full_name" type="text" className={inputClass} {...register("full_name")} />
          {errors.full_name && (
            <p className="mt-1 text-xs text-red-600">{errors.full_name.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="document_number" className="block text-sm font-medium text-slate-700">
            {isCompany ? "CNPJ" : "CPF"}{" "}
            <span className="font-normal text-slate-400">(opcional)</span>
          </label>
          <input
            id="document_number"
            type="text"
            inputMode="numeric"
            placeholder={isCompany ? "00.000.000/0000-00" : "000.000.000-00"}
            aria-describedby="document_number-help"
            className={inputClass}
            {...register("document_number")}
          />
          <p id="document_number-help" className="mt-1 text-xs text-slate-500">
            Identifica o cliente dentro do escritório e evita cadastro duplicado. Pode ficar em
            branco no primeiro contato.
          </p>
          {errors.document_number && (
            <p className="mt-1 text-xs text-red-600">{errors.document_number.message}</p>
          )}
        </div>

        {!isCompany && (
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="rg" className="block text-sm font-medium text-slate-700">
                RG <span className="font-normal text-slate-400">(opcional)</span>
              </label>
              <input id="rg" type="text" className={inputClass} {...register("rg")} />
            </div>
            <div>
              <label htmlFor="rg_issuer" className="block text-sm font-medium text-slate-700">
                Órgão emissor
              </label>
              <input
                id="rg_issuer"
                type="text"
                placeholder="SSP/SP"
                className={inputClass}
                {...register("rg_issuer")}
              />
            </div>
            <div>
              <label htmlFor="birth_date" className="block text-sm font-medium text-slate-700">
                Nascimento
              </label>
              <input id="birth_date" type="date" className={inputClass} {...register("birth_date")} />
            </div>
          </div>
        )}
      </fieldset>

      {!isCompany && (
        <fieldset className="space-y-4">
          <legend className="text-sm font-medium text-slate-900">
            Qualificação para a peça
            <span className="ml-2 font-normal text-slate-500">(CPC art. 319, II)</span>
          </legend>

          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="nationality" className="block text-sm font-medium text-slate-700">
                Nacionalidade
              </label>
              <input
                id="nationality"
                type="text"
                className={inputClass}
                {...register("nationality")}
              />
            </div>
            <div>
              <label htmlFor="marital_status" className="block text-sm font-medium text-slate-700">
                Estado civil
              </label>
              <select id="marital_status" className={selectClass} {...register("marital_status")}>
                <option value="">A informar</option>
                {MARITAL_STATUS_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="profession" className="block text-sm font-medium text-slate-700">
                Profissão
              </label>
              <input id="profession" type="text" className={inputClass} {...register("profession")} />
            </div>
          </div>
        </fieldset>
      )}

      <fieldset className="space-y-4">
        <legend className="text-sm font-medium text-slate-900">Contato</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">
              E-mail
            </label>
            <input id="email" type="email" className={inputClass} {...register("email")} />
            {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>}
          </div>
          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-slate-700">
              Telefone
            </label>
            <input
              id="phone"
              type="tel"
              placeholder="(11) 90000-0000"
              className={inputClass}
              {...register("phone")}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-sm font-medium text-slate-900">
          Endereço
          <span className="ml-2 font-normal text-slate-500">
            — define o foro do consumidor (CDC art. 101, I)
          </span>
        </legend>

        <div className="grid gap-4 sm:grid-cols-4">
          <div className="sm:col-span-3">
            <label htmlFor="address_street" className="block text-sm font-medium text-slate-700">
              Logradouro
            </label>
            <input
              id="address_street"
              type="text"
              className={inputClass}
              {...register("address_street")}
            />
          </div>
          <div>
            <label htmlFor="address_number" className="block text-sm font-medium text-slate-700">
              Número
            </label>
            <input
              id="address_number"
              type="text"
              className={inputClass}
              {...register("address_number")}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="address_complement"
              className="block text-sm font-medium text-slate-700"
            >
              Complemento
            </label>
            <input
              id="address_complement"
              type="text"
              className={inputClass}
              {...register("address_complement")}
            />
          </div>
          <div>
            <label htmlFor="address_district" className="block text-sm font-medium text-slate-700">
              Bairro
            </label>
            <input
              id="address_district"
              type="text"
              className={inputClass}
              {...register("address_district")}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-4">
          <div className="sm:col-span-2">
            <label htmlFor="address_city" className="block text-sm font-medium text-slate-700">
              Município
            </label>
            <input
              id="address_city"
              type="text"
              className={inputClass}
              {...register("address_city")}
            />
          </div>
          <div>
            <label htmlFor="address_state" className="block text-sm font-medium text-slate-700">
              UF
            </label>
            <select id="address_state" className={selectClass} {...register("address_state")}>
              <option value="">—</option>
              {BRAZILIAN_STATES.map((uf) => (
                <option key={uf} value={uf}>
                  {uf}
                </option>
              ))}
            </select>
            {errors.address_state && (
              <p className="mt-1 text-xs text-red-600">{errors.address_state.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="address_zip_code" className="block text-sm font-medium text-slate-700">
              CEP
            </label>
            <input
              id="address_zip_code"
              type="text"
              inputMode="numeric"
              placeholder="00000-000"
              className={inputClass}
              {...register("address_zip_code")}
            />
            {errors.address_zip_code && (
              <p className="mt-1 text-xs text-red-600">{errors.address_zip_code.message}</p>
            )}
          </div>
        </div>
      </fieldset>

      {formError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {formError}
        </p>
      )}

      <div className="flex justify-end gap-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancelar
          </button>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          {isSubmitting ? "Salvando..." : submitLabel}
        </button>
      </div>
    </form>
  );
}
