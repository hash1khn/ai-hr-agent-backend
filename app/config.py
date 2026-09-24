from functools import lru_cache
from urllib.parse import quote, unquote
import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = ""
    openai_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openai_model: str = ""
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openai_embedding_model: str = ""
    openai_base_url: str | None = None

    database_url: str = "postgres://hr:hr@localhost:5434/hr_agent"
    port: int = 3004
    cors_origins: str = "http://localhost:3000"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_ttl_hours: int = 24
    cookie_name: str = "hr_session"
    cookie_secure: bool = False
    environment: str = "development"

    default_temperature: float = 0.2
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieve_top_k: int = 5
    similarity_floor: float = 0.25
    max_upload_bytes: int = 10 * 1024 * 1024
    chat_rate_limit_per_minute: int = 20
    auth_rate_limit_per_minute: int = 10
    llm_timeout_seconds: float = 30.0
    max_uploads_per_day: int = 20
    max_upload_bytes_per_day: int = 50 * 1024 * 1024

    seed_on_start: bool = True

    @property
    def api_key(self) -> str | None:
        key = self.openrouter_api_key or self.openai_api_key
        if key and "your-key" not in key:
            return key
        return None

    @property
    def uses_openrouter(self) -> bool:
        return bool(self.openrouter_api_key) and "your-key" not in self.openrouter_api_key

    @property
    def chat_model(self) -> str:
        return self.openrouter_model or self.openai_model or "openai/gpt-4o-mini"

    @property
    def embedding_model(self) -> str:
        return (
            self.openrouter_embedding_model
            or self.openai_embedding_model
            or "openai/text-embedding-3-small"
        )

    @property
    def llm_base_url(self) -> str | None:
        if self.openai_base_url:
            return self.openai_base_url
        if self.uses_openrouter:
            return "https://openrouter.ai/api/v1"
        return None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    def validate_runtime_security(self) -> None:
        if not self.is_production():
            return
        placeholder = self.jwt_secret in {"", "change-me-to-a-long-random-string"}
        too_short = len(self.jwt_secret) < 32
        if placeholder or too_short:
            raise RuntimeError(
                "JWT_SECRET must be a unique string of at least 32 characters in production."
            )
        if not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production.")

    @property
    def is_remote_db(self) -> bool:
        return all(token not in self.database_url for token in ("localhost", "127.0.0.1"))

    @property
    def connect_timeout(self) -> int:
        return 15 if self.is_remote_db else 3

    @property
    def pool_timeout(self) -> int:
        return 20 if self.is_remote_db else 8

    @property
    def dsn(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]

        match = re.match(
            r"^(postgresql://)([^:]+):(.+)@([^:/@]+):(\d+)(/[^?]*)?(\?.*)?$",
            url,
        )
        if match:
            scheme, user, password, host, port, path, query = match.groups()
            password = quote(unquote(password), safe="")
            url = f"{scheme}{user}:{password}@{host}:{port}{path or ''}{query or ''}"

        if "supabase.co" in url and "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
