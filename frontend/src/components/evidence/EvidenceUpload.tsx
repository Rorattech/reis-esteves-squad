"use client";

import { useRef, useState } from "react";

import { api, ApiError } from "@/services/api";

/**
 * Mesma lista fechada do backend (backend/app/core/storage.py::ALLOWED_MIME_TYPES)
 * — a validação visual aqui é só conveniência de UX; a validação real (MIME,
 * tamanho, magic bytes) é sempre do backend (CLAUDE.md, seção 16).
 */
const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "text/plain",
]);
const MAX_UPLOAD_MB = 50;

interface EvidenceUploadProps {
  caseId: string;
  canWrite: boolean;
  onUploaded: () => void;
}

interface UploadFeedback {
  kind: "success" | "error";
  message: string;
}

/**
 * Área de upload da Central de Evidências (roadmap 3.4). Envia um ou mais
 * arquivos em sequência (a API recebe um por request), preservando o
 * original intacto — nunca existe URL pública para o arquivo enviado.
 */
export function EvidenceUpload({ caseId, canWrite, onUploaded }: EvidenceUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<UploadFeedback[]>([]);

  if (!canWrite) {
    return (
      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
        Seu papel atual permite apenas consultar o inventário de evidências.
      </p>
    );
  }

  function validateLocally(file: File): string | null {
    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      return `"${file.name}": tipo de arquivo não suportado. Aceitos: PDF, JPG, PNG, WebP e TXT.`;
    }
    if (file.size === 0) {
      return `"${file.name}": arquivo vazio não pode ser anexado como evidência.`;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      return `"${file.name}": excede o limite de ${MAX_UPLOAD_MB} MB.`;
    }
    return null;
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const results: UploadFeedback[] = [];
    for (const file of Array.from(files)) {
      const localError = validateLocally(file);
      if (localError) {
        results.push({ kind: "error", message: localError });
        continue;
      }
      setUploadingName(file.name);
      try {
        const uploaded = await api.uploadEvidence(caseId, file);
        results.push({
          kind: "success",
          message: uploaded.is_duplicate
            ? `"${file.name}" enviado — conteúdo idêntico a uma evidência já anexada (duplicado marcado).`
            : `"${file.name}" enviado e aguardando processamento.`,
        });
      } catch (error) {
        results.push({
          kind: "error",
          message:
            error instanceof ApiError
              ? `"${file.name}": ${error.message}`
              : `"${file.name}": falha inesperada no envio.`,
        });
      }
    }
    setUploadingName(null);
    setFeedback(results);
    if (inputRef.current) inputRef.current.value = "";
    if (results.some((item) => item.kind === "success")) onUploaded();
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-4">
        <label htmlFor="evidence-upload-input" className="block text-sm font-medium text-slate-700">
          Anexar evidências ao caso
        </label>
        <p className="mt-1 text-xs text-slate-500">
          PDF, JPG, PNG, WebP ou TXT — até {MAX_UPLOAD_MB} MB por arquivo. O arquivo original é
          preservado sem alteração; OCR e transcrição geram conteúdo derivado separado.
        </p>
        <input
          id="evidence-upload-input"
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,.webp,.txt,application/pdf,image/jpeg,image/png,image/webp,text/plain"
          disabled={uploadingName !== null}
          onChange={(event) => handleFiles(event.target.files)}
          className="mt-3 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-slate-700 disabled:opacity-60"
        />
        {uploadingName && (
          <p className="mt-2 text-sm text-blue-700" role="status">
            Enviando &quot;{uploadingName}&quot;...
          </p>
        )}
      </div>

      {feedback.length > 0 && (
        <ul className="space-y-1" aria-label="Resultado dos envios">
          {feedback.map((item, index) => (
            <li
              key={index}
              className={
                item.kind === "success"
                  ? "rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                  : "rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
              }
            >
              {item.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
