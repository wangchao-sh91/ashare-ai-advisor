"""Validated application settings loaded from the environment."""

from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BindMode(StrEnum):
    """Supported network exposure modes."""

    DIRECT = "direct"
    CONTAINER = "container"


class LogLevel(StrEnum):
    """Allowed application log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class McpTransport(StrEnum):
    """Approved Doubao MCP transport for the single-worker MVP."""

    STDIO = "stdio"


class ProviderMode(StrEnum):
    """Select real providers or deterministic verification fakes."""

    REAL = "real"
    FAKE = "fake"


class Settings(BaseSettings):
    """Runtime configuration with safe defaults for local development."""

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

    doubao_search_api_key: SecretStr | None = None
    doubao_search_access_key: SecretStr | None = None
    doubao_search_secret_key: SecretStr | None = None
    doubao_search_transport: McpTransport = McpTransport.STDIO
    doubao_search_timeout_seconds: float = Field(default=20, gt=0, le=120)
    doubao_search_max_retries: int = Field(default=2, ge=0, le=5)

    akshare_timeout_seconds: float = Field(default=20, gt=0, le=120)
    akshare_max_retries: int = Field(default=2, ge=0, le=5)
    akshare_max_workers: int = Field(default=4, ge=1, le=16)
    market_data_cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    cors_allowed_origins: list[HttpUrl] = Field(
        default_factory=lambda: [HttpUrl("http://127.0.0.1:5173")]
    )

    @field_validator(
        "deepseek_api_key",
        "deepseek_base_url",
        "deepseek_model",
        "doubao_search_api_key",
        "doubao_search_access_key",
        "doubao_search_secret_key",
        mode="before",
    )
    @classmethod
    def blank_optional_values_become_none(cls, value: Any) -> Any:
        """Treat redacted empty environment variables as missing configuration."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("deepseek_model", mode="after")
    @classmethod
    def normalize_model_id(cls, value: str | None) -> str | None:
        """Reject an effectively empty wire model identifier."""
        return value.strip() if value is not None else None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Accept a comma-separated environment value or a programmatic list."""
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("at least one CORS origin is required")
            return origins
        return value

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def validate_cors_origins(cls, origins: list[HttpUrl]) -> list[HttpUrl]:
        """Require origins without credentials, query strings, or fragments."""
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
        """Keep direct development loopback-only and container binding explicit."""
        direct_hosts = {"127.0.0.1", "localhost", "::1"}
        container_hosts = {"0.0.0.0", "::"}
        if self.api_host is None:
            self.api_host = "127.0.0.1" if self.bind_mode is BindMode.DIRECT else "0.0.0.0"
        elif self.bind_mode is BindMode.DIRECT and self.api_host not in direct_hosts:
            raise ValueError("direct bind mode requires a loopback API host")
        elif self.bind_mode is BindMode.CONTAINER and self.api_host not in container_hosts:
            raise ValueError("container bind mode requires an all-interface API host")
        return self

    @model_validator(mode="after")
    def validate_doubao_authentication(self) -> "Settings":
        """Accept exactly one complete official MCP authentication mode."""
        has_api_key = self.doubao_search_api_key is not None
        has_access_key = self.doubao_search_access_key is not None
        has_secret_key = self.doubao_search_secret_key is not None
        if has_access_key != has_secret_key:
            raise ValueError("Doubao search access key and secret key must be configured together")
        if has_api_key and has_access_key:
            raise ValueError("Doubao search API-key and AK/SK modes are mutually exclusive")
        return self

    def doubao_search_auth_configured(self) -> bool:
        """Return whether one complete official MCP authentication mode is configured."""
        return self.doubao_search_api_key is not None or (
            self.doubao_search_access_key is not None and self.doubao_search_secret_key is not None
        )

    def doubao_search_child_env(self) -> dict[str, str]:
        """Map product-level secrets to the fixed official child environment."""
        if self.doubao_search_api_key is not None:
            return {
                "ASK_ECHO_SEARCH_INFINITY_API_KEY": self.doubao_search_api_key.get_secret_value()
            }
        if self.doubao_search_access_key and self.doubao_search_secret_key:
            return {
                "VOLCENGINE_ACCESS_KEY": self.doubao_search_access_key.get_secret_value(),
                "VOLCENGINE_SECRET_KEY": self.doubao_search_secret_key.get_secret_value(),
            }
        return {}

    def missing_required_provider_settings(self) -> tuple[str, ...]:
        """Return missing readiness keys without exposing their values."""
        if self.provider_mode is ProviderMode.FAKE:
            return ()
        required = {
            "DEEPSEEK_API_KEY": self.deepseek_api_key,
            "DEEPSEEK_BASE_URL": self.deepseek_base_url,
            "DEEPSEEK_MODEL": self.deepseek_model,
            "DOUBAO_SEARCH_AUTH": self.doubao_search_auth_configured() or None,
        }
        return tuple(name for name, value in required.items() if value is None)

    def secret_values(self) -> tuple[str, ...]:
        """Return configured secrets for in-process log redaction."""
        return tuple(
            secret.get_secret_value()
            for secret in (
                self.deepseek_api_key,
                self.doubao_search_api_key,
                self.doubao_search_access_key,
                self.doubao_search_secret_key,
            )
            if secret is not None and secret.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    """Load and cache process-wide settings."""
    return Settings()
