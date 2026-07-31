"""Armazenamento privado dos arquivos originais de evidência (Fase 3.1).

Decisão de arquitetura registrada em
docs/adr/0001-evidence-storage-local-filesystem.md: sistema de arquivos
local, em diretório nunca servido como estático, com volume Docker dedicado
(ver infra/docker-compose.yml) — menor solução compatível com a stack atual
(CLAUDE.md, seção 3, não define um provedor de object storage para o MVP).
Trocar por S3/MinIO no futuro exige apenas uma nova implementação desta
mesma interface; nenhum código de app/services/evidence_service.py muda.

Todo acesso ao arquivo original passa por uma rota autenticada da API, nunca
por URL pública (ver app/api/v1/evidence.py).
"""

import uuid
from pathlib import Path

# mime_type -> extensão de armazenamento. Lista fechada e pequena de
# propósito: os tipos de evidência do MVP são prints de conversa/perfil
# (imagem), comprovantes/BOs (PDF ou imagem) e exportações de conversa em
# texto puro. A extensão do arquivo em disco vem sempre daqui — nunca do
# nome de arquivo informado no upload (CLAUDE.md, seção 15).
ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/plain": "txt",
}

# Assinaturas binárias (magic bytes) para conferir que o conteúdo real do
# arquivo é compatível com o mime_type declarado — um mime_type "image/png"
# com bytes de outra coisa é rejeitado antes de tocar o disco (roadmap 3.1:
# "Validar extensão, MIME type, tamanho e conteúdo quando aplicável").
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def sniff_content_matches_mime(mime_type: str, content: bytes) -> bool:
    """Confere se os bytes iniciais do arquivo são compatíveis com `mime_type`.

    text/plain não tem assinatura binária — em vez disso, rejeita conteúdo
    que pareça binário (byte nulo nos primeiros KB), o suficiente para pegar
    o caso comum de um arquivo binário apenas renomeado para .txt.

    Args:
        mime_type: Um dos tipos em ALLOWED_MIME_TYPES.
        content: Bytes do arquivo (o começo já basta).

    Returns:
        True se o conteúdo for compatível com o mime_type declarado.
    """
    if mime_type == "text/plain":
        return b"\x00" not in content[:4096]
    if mime_type == "image/webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    signatures = _SIGNATURES.get(mime_type)
    if signatures is None:
        return False
    return any(content.startswith(signature) for signature in signatures)


class EvidenceStorageError(RuntimeError):
    """Erro de armazenamento — nunca deve deixar o original em estado parcial."""


class EvidenceStorage:
    """Grava e lê originais de evidência num diretório privado local.

    Cada storage_key é escrita exatamente uma vez (open em modo "xb" —
    criação exclusiva): uma segunda escrita para a mesma key é tratada como
    erro de estado, nunca como sobrescrita silenciosa (roadmap 3.1: "Não
    modificar o arquivo original").
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def build_key(
        self, *, tenant_id: uuid.UUID, case_id: uuid.UUID, evidence_id: uuid.UUID, extension: str
    ) -> str:
        """Monta a storage_key determinística de um novo arquivo de evidência.

        O layout <tenant_id>/<case_id>/<evidence_id>/original.<ext> isola
        fisicamente cada tenant em seu próprio subdiretório — segunda camada
        de defesa além do filtro tenant_id nas queries (CLAUDE.md, seção 7).
        """
        return f"{tenant_id}/{case_id}/{evidence_id}/original.{extension}"

    def _resolve(self, storage_key: str) -> Path:
        resolved = (self._root / storage_key).resolve()
        if not resolved.is_relative_to(self._root):
            raise EvidenceStorageError(f"storage_key fora do diretório raiz: {storage_key!r}")
        return resolved

    def write_original(self, storage_key: str, content: bytes) -> None:
        """Grava o arquivo original — falha se a key já existir (nunca sobrescreve).

        Args:
            storage_key: Chave retornada por `build_key`.
            content: Bytes do arquivo já validados (mime, tamanho, conteúdo).

        Raises:
            EvidenceStorageError: Se a storage_key já existir no disco.
        """
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError as exc:
            raise EvidenceStorageError(
                f"storage_key já existe — original nunca é sobrescrito: {storage_key!r}"
            ) from exc

    def read_path(self, storage_key: str) -> Path:
        """Resolve o caminho absoluto de leitura de um original já gravado.

        Raises:
            EvidenceStorageError: Se o arquivo não existir no disco.
        """
        path = self._resolve(storage_key)
        if not path.is_file():
            raise EvidenceStorageError(
                f"original não encontrado no armazenamento: {storage_key!r}"
            )
        return path


def get_evidence_storage() -> EvidenceStorage:
    """Dependency FastAPI: instancia o EvidenceStorage a partir de Settings."""
    from app.core.config import settings

    return EvidenceStorage(Path(settings.evidence_storage_dir))
