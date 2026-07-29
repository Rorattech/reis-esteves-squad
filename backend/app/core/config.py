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

    # Nome do modelo usado pelos nós LangGraph do módulo Intake (CLAUDE.md,
    # seção 15 — nunca hardcoded no nó chamador, sempre via esta constante).
    intake_llm_model: str = "claude-sonnet-5"

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
