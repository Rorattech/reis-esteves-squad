"""Serviço de gestão de evidências — Fase 3.1, módulo evidence.

Toda função valida que o caso pertence ao tenant informado antes de ler ou
escrever (CLAUDE.md, seção 7) e grava uma entrada em audit_logs antes de
retornar (CLAUDE.md, seção 10) — inclusive para leituras de conteúdo
original (download), que fazem parte da cadeia de custódia (roadmap 3.1:
"auditoria integral de upload, acesso e processamento").

Nenhuma análise jurídica acontece aqui (roadmap 3.1) — apenas custódia:
receber, validar, armazenar intacto, inventariar e auditar.
"""

import hashlib
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_entry_to_orm, create_audit_entry
from app.core.storage import (
    ALLOWED_MIME_TYPES,
    EvidenceStorage,
    sniff_content_matches_mime,
)
from app.models.case import Case
from app.models.enums import EvidenceProcessingStatus
from app.models.evidence_file import EvidenceFile

_MODEL_USED_MANUAL = "n/a"


class EvidenceValidationError(ValueError):
    """Upload rejeitado na validação — mime, tamanho ou conteúdo inválido."""


async def _get_case_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> Case | None:
    return await session.scalar(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))


def _add_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    input_data: Any,
    output_data: Any,
    started_at: float,
    metadata: dict[str, Any],
) -> None:
    entry = create_audit_entry(
        actor_id=str(actor_id),
        action=action,
        module="evidence",
        input_data=input_data,
        output_data=output_data,
        model_used=_MODEL_USED_MANUAL,
        tokens_used=0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        actor="human",
        metadata={"entity": "evidence", **metadata},
    )
    session.add(audit_entry_to_orm(entry, tenant_id=tenant_id, case_id=case_id))


def validate_upload(
    *, mime_type: str, size_bytes: int, content: bytes, max_upload_mb: int
) -> str:
    """Valida mime type, tamanho e conteúdo de um upload de evidência.

    Args:
        mime_type: Content-Type declarado no upload.
        size_bytes: Tamanho real do conteúdo recebido.
        content: Bytes do arquivo.
        max_upload_mb: Limite de tamanho em MB (settings.backend_max_upload_mb).

    Returns:
        Extensão de armazenamento derivada do mime_type validado.

    Raises:
        EvidenceValidationError: Se qualquer validação falhar.
    """
    extension = ALLOWED_MIME_TYPES.get(mime_type)
    if extension is None:
        allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise EvidenceValidationError(
            f"Tipo de arquivo não suportado ({mime_type}). Tipos aceitos: {allowed}."
        )
    if size_bytes == 0:
        raise EvidenceValidationError("Arquivo vazio não pode ser anexado como evidência.")
    if size_bytes > max_upload_mb * 1024 * 1024:
        raise EvidenceValidationError(f"Arquivo excede o limite de {max_upload_mb} MB.")
    if not sniff_content_matches_mime(mime_type, content):
        raise EvidenceValidationError(
            "O conteúdo do arquivo não corresponde ao tipo declarado."
        )
    return extension


async def store_evidence(
    session: AsyncSession,
    storage: EvidenceStorage,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    original_filename: str,
    mime_type: str,
    content: bytes,
    origin: str,
    max_upload_mb: int,
    client_host: str | None,
) -> EvidenceFile | None:
    """Valida, armazena e inventaria um novo arquivo de evidência.

    O original é gravado exatamente uma vez (EvidenceStorage.write_original
    nunca sobrescreve) e o registro nasce com status "received". Uploads com
    o mesmo SHA-256 de outra evidência do tenant são aceitos, mas marcados
    com duplicate_of_id apontando para a primeira ocorrência.

    Args:
        session: Sessão do banco já escopada por tenant.
        storage: Armazenamento privado de originais.
        tenant_id: Tenant autenticado da request.
        case_id: Caso ao qual a evidência pertence.
        actor_id: Usuário autenticado que realizou o upload.
        original_filename: Nome do arquivo como enviado (truncado a 255).
        mime_type: Content-Type declarado no upload.
        content: Bytes do arquivo.
        origin: De onde a evidência veio (ex.: "upload_portal").
        max_upload_mb: Limite de tamanho em MB.
        client_host: IP de origem da request, para a cadeia de custódia.

    Returns:
        EvidenceFile criado, ou None se o caso não existir neste tenant.

    Raises:
        EvidenceValidationError: Se mime, tamanho ou conteúdo forem inválidos.
    """
    started_at = time.monotonic()
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None

    extension = validate_upload(
        mime_type=mime_type,
        size_bytes=len(content),
        content=content,
        max_upload_mb=max_upload_mb,
    )
    sha256_hash = hashlib.sha256(content).hexdigest()

    duplicate_of = await session.scalar(
        select(EvidenceFile)
        .where(
            EvidenceFile.tenant_id == tenant_id,
            EvidenceFile.sha256_hash == sha256_hash,
        )
        .order_by(EvidenceFile.created_at)
        .limit(1)
    )

    evidence_id = uuid.uuid4()
    storage_key = storage.build_key(
        tenant_id=tenant_id, case_id=case_id, evidence_id=evidence_id, extension=extension
    )

    evidence = EvidenceFile(
        id=evidence_id,
        tenant_id=tenant_id,
        case_id=case_id,
        uploaded_by=actor_id,
        original_filename=original_filename[:255],
        mime_type=mime_type,
        extension=extension,
        size_bytes=len(content),
        sha256_hash=sha256_hash,
        storage_key=storage_key,
        origin=origin[:50],
        status=EvidenceProcessingStatus.RECEIVED,
        duplicate_of_id=duplicate_of.id if duplicate_of is not None else None,
    )
    session.add(evidence)
    await session.flush()

    # Disco só depois do flush: se o INSERT falhar, nada foi gravado; se o
    # disco falhar, o rollback da sessão desfaz o registro do inventário.
    storage.write_original(storage_key, content)

    _add_audit(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=actor_id,
        action="anexou arquivo de evidência ao caso",
        # Nunca o conteúdo em claro (CLAUDE.md, seção 12) — só metadados.
        input_data={
            "original_filename": evidence.original_filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256_hash": sha256_hash,
            "origin": evidence.origin,
        },
        output_data={"evidence_id": str(evidence_id), "status": evidence.status.value},
        started_at=started_at,
        metadata={
            "evidence_id": str(evidence_id),
            "case_id": str(case_id),
            "client_host": client_host,
            "duplicate_of_id": str(duplicate_of.id) if duplicate_of is not None else None,
        },
    )

    await session.commit()
    await session.refresh(evidence)
    return evidence


async def list_evidence(
    session: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> list[EvidenceFile] | None:
    """Lista o inventário de evidências de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.

    Returns:
        Evidências mais recentes primeiro, ou None se o caso não existir
        neste tenant.
    """
    case = await _get_case_for_tenant(session, tenant_id, case_id)
    if case is None:
        return None
    items = await session.scalars(
        select(EvidenceFile)
        .where(EvidenceFile.tenant_id == tenant_id, EvidenceFile.case_id == case_id)
        .order_by(EvidenceFile.created_at.desc())
    )
    return list(items.all())


async def get_evidence(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> EvidenceFile | None:
    """Retorna uma evidência específica de um caso do tenant autenticado.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.
        evidence_id: ID da evidência.

    Returns:
        A evidência, ou None se não existir neste tenant/caso.
    """
    return await session.scalar(
        select(EvidenceFile).where(
            EvidenceFile.tenant_id == tenant_id,
            EvidenceFile.case_id == case_id,
            EvidenceFile.id == evidence_id,
        )
    )


async def record_evidence_access(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    access_kind: str,
    client_host: str | None,
) -> None:
    """Registra na auditoria um acesso ao conteúdo original de uma evidência.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request.
        case_id: ID do caso.
        evidence_id: ID da evidência acessada.
        actor_id: Usuário autenticado que acessou.
        access_kind: "download" ou "view".
        client_host: IP de origem da request.
    """
    started_at = time.monotonic()
    _add_audit(
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=actor_id,
        action=f"acessou o conteúdo original de uma evidência ({access_kind})",
        input_data={"evidence_id": str(evidence_id), "access_kind": access_kind},
        output_data={"evidence_id": str(evidence_id)},
        started_at=started_at,
        metadata={
            "evidence_id": str(evidence_id),
            "case_id": str(case_id),
            "access_kind": access_kind,
            "client_host": client_host,
        },
    )
    await session.commit()
