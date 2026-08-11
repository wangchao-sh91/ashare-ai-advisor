import pytest
from pydantic import HttpUrl, SecretStr, ValidationError

from app.core.settings import DOUBAO_SEARCH_ENDPOINT, BindMode, ProviderMode, Settings


def test_provider_settings_and_documented_cache_defaults() -> None:
    settings = Settings(
        _env_file=None,
        tushare_token=SecretStr("market-secret"),
        doubao_search_api_key=SecretStr("search-secret"),
    )
    assert str(settings.doubao_search_endpoint) == DOUBAO_SEARCH_ENDPOINT
    assert settings.price_cache_ttl_seconds == 21600
    assert settings.corporate_event_cache_ttl_seconds == 1800
    assert settings.financial_search_cache_ttl_seconds == 86400
    assert settings.index_search_cache_ttl_seconds == 3600
    assert settings.provider_cache_max_entries == 512


def test_missing_provider_names_and_fake_mode_are_secret_safe() -> None:
    missing = Settings(_env_file=None).missing_required_provider_settings()
    assert missing == (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "TUSHARE_TOKEN",
        "DOUBAO_SEARCH_API_KEY",
    )
    assert (
        Settings(
            _env_file=None, provider_mode=ProviderMode.FAKE
        ).missing_required_provider_settings()
        == ()
    )


def test_secrets_are_available_only_for_log_redaction() -> None:
    settings = Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("model-secret"),
        tushare_token=SecretStr("market-secret"),
        doubao_search_api_key=SecretStr("search-secret"),
    )
    assert settings.secret_values() == ("model-secret", "market-secret", "search-secret")
    rendered = repr(settings)
    assert "model-secret" not in rendered
    assert "market-secret" not in rendered
    assert "search-secret" not in rendered


def test_ranges_endpoint_and_bind_mode_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tushare_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, doubao_search_max_concurrency=6)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, doubao_search_endpoint=HttpUrl("https://example.com/search"))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, bind_mode=BindMode.DIRECT, api_host="0.0.0.0")
    assert Settings(_env_file=None, bind_mode=BindMode.CONTAINER).api_host == "0.0.0.0"


def test_cors_and_blank_secrets_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    settings = Settings(_env_file=None)
    assert settings.tushare_token is None
    assert [str(item) for item in settings.cors_allowed_origins] == [
        "http://127.0.0.1:5173/",
        "http://localhost:5173/",
    ]
