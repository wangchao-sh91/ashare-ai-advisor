import httpx
import pytest
from pydantic import HttpUrl, SecretStr

from app.agent.orchestrator import OrchestrationResult, ProgressCallback
from app.api.chat_models import ChatRequest
from app.core.runtime import ProviderRuntime
from app.core.settings import Settings
from app.main import create_app


class ReadyOrchestrator:
    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        del request, progress
        raise AssertionError("readiness test must not invoke orchestration")


def configured_settings() -> Settings:
    return Settings(
        deepseek_api_key=SecretStr("model-secret-value"),
        deepseek_base_url=HttpUrl("https://model.example.com/v1"),
        deepseek_model="deepseek-wire-model",
        tushare_token=SecretStr("market-secret-value"),
        doubao_search_api_key=SecretStr("search-secret-value"),
    )


@pytest.mark.asyncio
async def test_health_reports_process_liveness_without_configuration() -> None:
    app = create_app(Settings(_env_file=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_lists_only_missing_configuration_names() -> None:
    app = create_app(Settings(_env_file=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "missing": [
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_MODEL",
            "TUSHARE_TOKEN",
            "DOUBAO_SEARCH_API_KEY",
            "ORCHESTRATOR",
        ],
        "providers": {},
    }


@pytest.mark.asyncio
async def test_readiness_is_secret_safe_and_does_not_consume_search_quota() -> None:
    orchestrator = ReadyOrchestrator()
    runtime = ProviderRuntime(orchestrator=orchestrator)  # type: ignore[arg-type]
    app = create_app(
        configured_settings(),
        provider_runtime=runtime,
        orchestrator=orchestrator,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/ready")
        second = await client.get("/ready")
    assert first.status_code == second.status_code == 200
    assert first.json() == {
        "status": "ready",
        "missing": [],
        "providers": {"tushare": "configured", "doubao_search": "usable"},
    }
    for secret in ("model-secret-value", "market-secret-value", "search-secret-value"):
        assert secret not in first.text
