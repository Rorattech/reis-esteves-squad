"""Configurações centrais do backend, carregadas via variáveis de ambiente."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> raiz do repo (prompts/ e orchestrator/ são
# irmãos de backend/, ver backend/Dockerfile). Em Docker, prompts/ é copiado
# para /app/prompts; em dev local, prompts/ fica um nível acima de backend/.
_LOCAL_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configurações da aplicação FastAPI.

    Todos os valores são lidos de variáveis de ambiente (ou de um arquivo
    .env em desenvolvimento) — nunca hardcoded no código.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_env: str = "development"
    backend_secret_key: str
    backend_jwt_algorithm: str = "HS256"
    backend_jwt_access_token_expire_minutes: int = 15
    backend_jwt_refresh_token_expire_days: int = 7
    backend_cors_origins: str = "http://localhost:3000"
    backend_max_upload_mb: int = 50
    backend_rate_limit_per_minute: int = 60

    # Diretório privado (nunca servido como estático — ver app/core/storage.py
    # e docs/adr/0001-evidence-storage-local-filesystem.md) onde os originais
    # de evidência são gravados uma única vez, fora do bind mount de código
    # (ver volume "evidence_storage" em infra/docker-compose.yml).
    evidence_storage_dir: str = "/app/storage/evidence"

    # Nome do modelo usado pelos nós LangGraph do módulo Intake (CLAUDE.md,
    # seção 15 — nunca hardcoded no nó chamador, sempre via esta constante).
    intake_llm_model: str = "claude-sonnet-5"

    # Nome do modelo usado pelos nós LangGraph do módulo Evidence (documental
    # e specialist — Fase 3.3).
    evidence_llm_model: str = "claude-sonnet-5"

    # OCR gerenciado das evidências (Fase 3.2) — decisão e tratamento de
    # transferência internacional em docs/adr/0003-ocr-google-cloud-vision.md.
    google_vision_api_key: str | None = None
    google_vision_endpoint: str = "https://vision.googleapis.com/v1"
    google_vision_timeout_seconds: float = 30.0
    # files:annotate (síncrono, o único que aceita API key) anota no máximo 5
    # páginas por requisição — ver app/core/vision.py.
    google_vision_pages_per_request: int = 5
    # Teto defensivo de páginas submetidas a OCR por PDF escaneado: evita que
    # um upload de 50MB vire dezenas de chamadas cobradas.
    extraction_max_ocr_pages: int = 10
    # Abaixo deste patamar de confiança, o texto derivado é gravado com
    # `low_confidence=True` e entra na fila de conferência humana. O sistema
    # NUNCA reprocessa por conta própria nem "melhora" o texto com IA — apenas
    # sinaliza que a leitura automática é insuficiente (CLAUDE.md, seção 2).
    extraction_low_confidence_threshold: float = 0.75

    database_url: str
    redis_url: str

    # Override explícito (ex.: deploy com outro layout de diretórios). Se
    # None, core/prompts.py resolve entre /app/prompts (Docker) e
    # <raiz-do-repo>/prompts (dev local) — ver Settings.prompts_dir_path.
    prompts_dir: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna a whitelist de origens CORS como lista de strings."""
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def prompts_dir_path(self) -> Path:
        """Resolve o diretório prompts/, em Docker ou em dev local.

        Returns:
            Caminho para o diretório prompts/ que existir primeiro, entre
            `prompts_dir` (se definido), `/app/prompts` (Docker — ver
            backend/Dockerfile) e `<raiz-do-repo>/prompts` (dev local).

        Raises:
            FileNotFoundError: Se nenhum dos candidatos existir.
        """
        candidates = [
            Path(self.prompts_dir) if self.prompts_dir else None,
            Path("/app/prompts"),
            _LOCAL_REPO_ROOT / "prompts",
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_dir():
                return candidate
        raise FileNotFoundError(
            "Diretório prompts/ não encontrado — defina PROMPTS_DIR ou verifique "
            "se o repositório está no layout esperado (ver backend/app/core/config.py)."
        )


settings = Settings()
