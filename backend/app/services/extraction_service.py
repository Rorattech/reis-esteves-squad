"""Serviço do pipeline de extração de evidências (Fase 3.2) e revisão humana
do texto extraído (Fase 3.5).

O pipeline roda fora do ciclo da request (BackgroundTasks — ver ADR 0002),
com sessão própria escopada pelo tenant autenticado no upload. Transições:
received/processed/failed -> processing -> processed | failed. Toda execução
gera uma linha imutável em evidence_extractions e uma entrada em audit_logs;
falhas nunca apagam nem alteram o original (roadmap 3.2).

Logs e auditoria carregam apenas metadados e hashes — nunca o texto extraído
nem o conteúdo do original (CLAUDE.md, seção 12).
"""

import hashlib
import time
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.db import tenant_scoped_session
from app.core.extraction import ExtractionError, extract_content
from app.core.storage import EvidenceStorage
from app.models.enums import EvidenceProcessingStatus, ExtractionOutcome, ExtractionReviewVerdict
from app.models.evidence_extraction import EvidenceExtraction, EvidenceExtractionReview
from app.models.evidence_file import EvidenceFile

logger = structlog.get_logger()

_MODEL_USED_PIPELINE = "n/a"


def _add_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor: str,
    actor_id: str,
    action: str,
    input_data: Any,
    output_data: Any,
    started_at: float,
    metadata: dict[str, Any],
) -> None:
    entry = create_audit_entry(
        actor_id=actor_id,
        action=action,
        module="evidence",
        input_data=input_data,
        output_data=output_data,
        model_used=_MODEL_USED_PIPELINE,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor=actor,  # type: ignore[arg-type]
        metadata={"entity": "evidence", **metadata},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))


async def process_evidence(
    tenant_id: uuid.UUID,
    evidence_id: uuid.UUID,
    storage: EvidenceStorage,
) -> None:
    """Executa o pipeline de extração de uma evidência, em background.

    Abre a própria sessão (a da request já fechou), marca a evidência como
    "processing", roda o extrator adequado ao mime_type e grava o resultado
    como artefato derivado — sucesso ou falha, sempre com auditoria. Nunca
    levanta exceção para o chamador (BackgroundTasks não tem retry): falhas
    terminam com status "failed" rastreável.

    Args:
        tenant_id: Tenant autenticado no upload — nunca inferido de input.
        evidence_id: Evidência a processar.
        storage: Armazenamento privado dos originais.
    """
    started_at = time.monotonic()
    async with tenant_scoped_session(tenant_id) as session:
        evidence = await session.scalar(
            select(EvidenceFile).where(
                EvidenceFile.tenant_id == tenant_id, EvidenceFile.id == evidence_id
            )
        )
        if evidence is None:
            logger.warning(
                "evidence.extraction.not_found",
                tenant_id=str(tenant_id),
                evidence_id=str(evidence_id),
            )
            return
        if evidence.status == EvidenceProcessingStatus.PROCESSING:
            logger.info(
                "evidence.extraction.already_processing",
                tenant_id=str(tenant_id),
                evidence_id=str(evidence_id),
            )
            return

        evidence.status = EvidenceProcessingStatus.PROCESSING
        await session.commit()

        try:
            content = storage.read_path(evidence.storage_key).read_bytes()
            result = extract_content(evidence.mime_type, content)
        except Exception as exc:
            # Mensagem técnica curta — nunca conteúdo do documento nos logs.
            error_message = str(exc) if isinstance(exc, ExtractionError) else type(exc).__name__
            extraction = EvidenceExtraction(
                tenant_id=tenant_id,
                case_id=evidence.case_id,
                evidence_id=evidence.id,
                kind="unknown",
                outcome=ExtractionOutcome.FAILED,
                tool_name="pipeline",
                tool_version="n/a",
                input_sha256=evidence.sha256_hash,
                duration_ms=int((time.monotonic() - started_at) * 1000),
                error_message=error_message,
            )
            evidence.status = EvidenceProcessingStatus.FAILED
            session.add(extraction)
            await session.flush()
            _add_audit(
                session,
                tenant_id=tenant_id,
                case_id=evidence.case_id,
                actor="system",
                actor_id="extraction_pipeline",
                action="falhou a extração de conteúdo da evidência",
                input_data={"evidence_id": str(evidence.id), "mime_type": evidence.mime_type},
                output_data={"error": error_message},
                started_at=started_at,
                metadata={
                    "evidence_id": str(evidence.id),
                    "extraction_id": str(extraction.id),
                    "outcome": "failed",
                },
            )
            await session.commit()
            logger.warning(
                "evidence.extraction.failed",
                tenant_id=str(tenant_id),
                evidence_id=str(evidence.id),
                error=error_message,
            )
            return

        extraction = EvidenceExtraction(
            tenant_id=tenant_id,
            case_id=evidence.case_id,
            evidence_id=evidence.id,
            kind=result.kind,
            outcome=ExtractionOutcome.SUCCEEDED,
            extracted_text=result.text,
            confidence=result.confidence,
            limitations=result.limitations,
            tool_name=result.tool_name,
            tool_version=result.tool_version,
            input_sha256=evidence.sha256_hash,
            output_sha256=hashlib.sha256(result.text.encode()).hexdigest(),
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )
        evidence.status = EvidenceProcessingStatus.PROCESSED
        session.add(extraction)
        await session.flush()
        _add_audit(
            session,
            tenant_id=tenant_id,
            case_id=evidence.case_id,
            actor="system",
            actor_id="extraction_pipeline",
            action="extraiu conteúdo derivado da evidência",
            input_data={"evidence_id": str(evidence.id), "mime_type": evidence.mime_type},
            # Hashes e métricas — nunca o texto extraído (CLAUDE.md, seção 12).
            output_data={
                "extraction_id": str(extraction.id),
                "kind": result.kind,
                "confidence": result.confidence,
                "output_sha256": extraction.output_sha256,
                "text_chars": len(result.text),
            },
            started_at=started_at,
            metadata={
                "evidence_id": str(evidence.id),
                "extraction_id": str(extraction.id),
                "outcome": "succeeded",
                "tool": f"{result.tool_name} {result.tool_version}",
            },
        )
        await session.commit()
        logger.info(
            "evidence.extraction.succeeded",
            tenant_id=str(tenant_id),
            evidence_id=str(evidence.id),
            kind=result.kind,
            confidence=result.confidence,
        )


async def list_extractions(
    session: AsyncSession, *, tenant_id: uuid.UUID, evidence_id: uuid.UUID
) -> list[EvidenceExtraction]:
    """Lista as execuções de extração de uma evidência, mais recentes primeiro.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        evidence_id: Evidência dona dos artefatos.

    Returns:
        Execuções de extração da evidência (sucesso e falha).
    """
    rows = await session.scalars(
        select(EvidenceExtraction)
        .options(selectinload(EvidenceExtraction.reviews))
        .where(
            EvidenceExtraction.tenant_id == tenant_id,
            EvidenceExtraction.evidence_id == evidence_id,
        )
        .order_by(EvidenceExtraction.created_at.desc())
    )
    return list(rows.all())


async def review_extraction(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    extraction_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    verdict: ExtractionReviewVerdict,
    note: str | None,
) -> EvidenceExtractionReview | None:
    """Registra a revisão humana de um texto extraído — sem substituir nada.

    A correção humana é um registro auditado apontando o erro; o texto
    derivado e o original permanecem intactos (roadmap 3.5).

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: Caso ao qual a evidência pertence.
        extraction_id: Execução de extração revisada.
        reviewer_id: Advogado/usuário que revisou.
        verdict: confirmed ou extraction_error.
        note: Observação livre do revisor.

    Returns:
        A revisão criada, ou None se a extração não existir neste tenant/caso.
    """
    started_at = time.monotonic()
    extraction = await session.scalar(
        select(EvidenceExtraction).where(
            EvidenceExtraction.tenant_id == tenant_id,
            EvidenceExtraction.case_id == case_id,
            EvidenceExtraction.id == extraction_id,
        )
    )
    if extraction is None:
        return None

    review = EvidenceExtractionReview(
        tenant_id=tenant_id,
        case_id=case_id,
        extraction_id=extraction_id,
        reviewer_id=reviewer_id,
        verdict=verdict,
        note=note,
    )
    session.add(review)
    await session.flush()
    _add_audit(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor="human",
        actor_id=str(reviewer_id),
        action=(
            "confirmou o texto extraído da evidência"
            if verdict == ExtractionReviewVerdict.CONFIRMED
            else "apontou erro de extração no texto derivado da evidência"
        ),
        input_data={"extraction_id": str(extraction_id), "verdict": verdict.value},
        output_data={"review_id": str(review.id)},
        started_at=started_at,
        metadata={
            "evidence_id": str(extraction.evidence_id),
            "extraction_id": str(extraction_id),
            "review_id": str(review.id),
            "verdict": verdict.value,
        },
    )
    await session.commit()
    await session.refresh(review)
    return review
