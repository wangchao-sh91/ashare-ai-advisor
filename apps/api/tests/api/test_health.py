import httpx
import pytest
from pydantic import HttpUrl, SecretStr

from app.agent.orchestrator import OrchestrationResult, ProgressCallback
from app.api.chat_models import ChatRequest
from app.core.settings import Settings
from app.main import create_app


class ReadyRuntime:
    is_ready = True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


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
        doubao_search_api_key=SecretStr("search-secret-value"),
    )


@pytest.mark.asyncio
async def test_health_reports_process_liveness_without_configuration() -> None:
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_lists_only_missing_configuration_names() -> None:
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["missing"] == [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DOUBAO_SEARCH_AUTH",
        "ORCHESTRATOR",
    ]
    assert set(payload) == {"status", "missing"}


@pytest.mark.asyncio
async def test_readiness_never_exposes_configured_values() -> None:
    settings = configured_settings()
    app = create_app(
        settings,
        search_runtime=ReadyRuntime(),
        orchestrator=ReadyOrchestrator(),
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "missing": []}
    serialized = response.text
    for sensitive_value in (
        "model-secret-value",
        "search-secret-value",
        "model.example.com",
        "deepseek-wire-model",
    ):
        assert sensitive_value not in serialized


@pytest.mark.asyncio
async def test_readiness_reports_mcp_initialization_without_secrets() -> None:
    settings = configured_settings()
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["missing"] == ["DOUBAO_SEARCH_MCP", "ORCHESTRATOR"]
    assert "search-secret-value" not in response.text
