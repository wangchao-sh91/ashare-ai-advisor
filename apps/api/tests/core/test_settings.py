import pytest
from pydantic import HttpUrl, SecretStr, ValidationError

from app.core.settings import BindMode, McpTransport, Settings


def test_direct_settings_parse_cors_and_redacted_provider_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "")
    settings = Settings()

    assert settings.api_host == "127.0.0.1"
    assert [str(origin) for origin in settings.cors_allowed_origins] == [
        "http://127.0.0.1:5173/",
        "http://localhost:5173/",
    ]
    assert "DEEPSEEK_API_KEY" in settings.missing_required_provider_settings()


def test_container_mode_selects_container_host() -> None:
    settings = Settings(bind_mode=BindMode.CONTAINER)

    assert settings.api_host == "0.0.0.0"


@pytest.mark.parametrize(
    ("bind_mode", "api_host"),
    [(BindMode.DIRECT, "0.0.0.0"), (BindMode.CONTAINER, "127.0.0.1")],
)
def test_bind_mode_rejects_unsafe_host(bind_mode: BindMode, api_host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(bind_mode=bind_mode, api_host=api_host)


def test_settings_validate_ranges_and_cors_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(akshare_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins=[HttpUrl("https://example.com/path")])


def test_secret_values_are_unwrapped_only_for_redaction() -> None:
    settings = Settings(
        deepseek_api_key=SecretStr("model-secret"),
        doubao_search_api_key=SecretStr("search-secret"),
    )

    assert settings.secret_values() == ("model-secret", "search-secret")
    assert "model-secret" not in repr(settings)


def test_doubao_mcp_uses_fixed_stdio_and_maps_api_key() -> None:
    settings = Settings(doubao_search_api_key=SecretStr("search-secret"))

    assert settings.doubao_search_transport is McpTransport.STDIO
    assert settings.doubao_search_auth_configured()
    assert settings.doubao_search_child_env() == {
        "ASK_ECHO_SEARCH_INFINITY_API_KEY": "search-secret"  # pragma: allowlist secret
    }


def test_doubao_mcp_accepts_complete_aksk_but_rejects_mixed_or_partial_auth() -> None:
    settings = Settings(
        doubao_search_access_key=SecretStr("access"),
        doubao_search_secret_key=SecretStr("secret"),
    )
    assert settings.doubao_search_child_env() == {
        "VOLCENGINE_ACCESS_KEY": "access",
        "VOLCENGINE_SECRET_KEY": "secret",  # pragma: allowlist secret
    }

    with pytest.raises(ValidationError):
        Settings(doubao_search_access_key=SecretStr("access"))
    with pytest.raises(ValidationError):
        Settings(
            doubao_search_api_key=SecretStr("api"),
            doubao_search_access_key=SecretStr("access"),
            doubao_search_secret_key=SecretStr("secret"),
        )
