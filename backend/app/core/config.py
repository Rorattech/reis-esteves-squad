"""Configurações centrais do backend, carregadas via variáveis de ambiente."""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    database_url: str
    redis_url: str

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna a whitelist de origens CORS como lista de strings."""
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
