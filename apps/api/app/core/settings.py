"""Validated, secret-safe application and provider settings."""

from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DOUBAO_SEARCH_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"


class BindMode(StrEnum):
    DIRECT = "direct"
    CONTAINER = "container"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProviderMode(StrEnum):
    REAL = "real"
    FAKE = "fake"


class Settings(BaseSettings):
    """Runtime configuration; provider secrets are never rendered by the app."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        enable_decoding=False,
    )

    app_env: str = "development"
    provider_mode: ProviderMode = ProviderMode.REAL
    bind_mode: BindMode = BindMode.DIRECT
    api_host: str | None = None
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = LogLevel.INFO

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: HttpUrl | None = None
    deepseek_model: str | None = None
    deepseek_temperature: float = Field(default=0.1, ge=0, le=1)
    deepseek_max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    deepseek_timeout_seconds: float = Field(default=60, gt=0, le=300)
    deepseek_max_retries: int = Field(default=2, ge=0, le=5)

    tushare_token: SecretStr | None = None
    tushare_timeout_seconds: float = Field(default=20, gt=0, le=120)
    tushare_max_retries: int = Field(default=1, ge=0, le=3)
    tushare_max_workers: int = Field(default=4, ge=1, le=16)
    price_cache_ttl_seconds: int = Field(default=21600, ge=1, le=604800)

    doubao_search_api_key: SecretStr | None = None
    doubao_search_endpoint: HttpUrl = HttpUrl(DOUBAO_SEARCH_ENDPOINT)
    doubao_search_timeout_seconds: float = Field(default=20, gt=0, le=120)
    doubao_search_max_retries: int = Field(default=2, ge=0, le=5)
    doubao_search_max_concurrency: int = Field(default=4, ge=1, le=5)
    doubao_search_result_count: int = Field(default=5, ge=1, le=50)
    corporate_event_cache_ttl_seconds: int = Field(default=1800, ge=1, le=86400)
    financial_search_cache_ttl_seconds: int = Field(default=86400, ge=1, le=604800)
    index_search_cache_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    provider_cache_max_entries: int = Field(default=512, ge=1, le=10000)

    cors_allowed_origins: list[HttpUrl] = Field(
        default_factory=lambda: [HttpUrl("http://127.0.0.1:5173")]
    )

    @field_validator(
        "deepseek_api_key",
        "deepseek_base_url",
        "deepseek_model",
        "tushare_token",
        "doubao_search_api_key",
        mode="before",
    )
    @classmethod
    def blank_optional_values_become_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("deepseek_model", mode="after")
    @classmethod
    def normalize_model_id(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("doubao_search_endpoint", mode="after")
    @classmethod
    def require_official_search_endpoint(cls, value: HttpUrl) -> HttpUrl:
        if str(value) != DOUBAO_SEARCH_ENDPOINT:
            raise ValueError("Doubao Search endpoint must be the approved official endpoint")
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("at least one CORS origin is required")
            return origins
        return value

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def validate_cors_origins(cls, origins: list[HttpUrl]) -> list[HttpUrl]:
        if not origins:
            raise ValueError("at least one CORS origin is required")
        for origin in origins:
            if origin.username or origin.password or origin.query or origin.fragment:
                raise ValueError("CORS origins cannot contain credentials, queries, or fragments")
            if origin.path not in (None, "/"):
                raise ValueError("CORS origins cannot contain a path")
        return origins

    @model_validator(mode="after")
    def validate_bind_mode(self) -> "Settings":
        direct_hosts = {"127.0.0.1", "localhost", "::1"}
        container_hosts = {"0.0.0.0", "::"}
        if self.api_host is None:
            self.api_host = "127.0.0.1" if self.bind_mode is BindMode.DIRECT else "0.0.0.0"
        elif self.bind_mode is BindMode.DIRECT and self.api_host not in direct_hosts:
            raise ValueError("direct bind mode requires a loopback API host")
        elif self.bind_mode is BindMode.CONTAINER and self.api_host not in container_hosts:
            raise ValueError("container bind mode requires an all-interface API host")
        return self

    def missing_required_provider_settings(self) -> tuple[str, ...]:
        if self.provider_mode is ProviderMode.FAKE:
            return ()
        required = {
            "DEEPSEEK_API_KEY": self.deepseek_api_key,
            "DEEPSEEK_BASE_URL": self.deepseek_base_url,
            "DEEPSEEK_MODEL": self.deepseek_model,
            "TUSHARE_TOKEN": self.tushare_token,
            "DOUBAO_SEARCH_API_KEY": self.doubao_search_api_key,
        }
        return tuple(name for name, value in required.items() if value is None)

    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            secret.get_secret_value()
            for secret in (
                self.deepseek_api_key,
                self.tushare_token,
                self.doubao_search_api_key,
            )
            if secret is not None and secret.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
