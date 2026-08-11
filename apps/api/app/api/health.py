"""Process health and secret-safe provider readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.core.runtime import ProviderRuntime
from app.core.settings import Settings
from app.providers.search_gateway import SearchReadiness

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ready", "not_ready"]
    missing: list[str]
    providers: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request) -> ReadinessResponse | JSONResponse:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("application settings are unavailable")
    missing = list(settings.missing_required_provider_settings())
    runtime = getattr(request.app.state, "provider_runtime", None)
    provider_states: dict[str, str] = {}
    if isinstance(runtime, ProviderRuntime):
        provider_states["tushare"] = "configured"
        provider_states["doubao_search"] = runtime.search_readiness.value
        if runtime.search_readiness in {
            SearchReadiness.QUOTA_UNAVAILABLE,
            SearchReadiness.UNAVAILABLE,
        }:
            missing.append(f"DOUBAO_SEARCH_{runtime.search_readiness.value.upper()}")
    if getattr(request.app.state, "orchestrator", None) is None:
        missing.append("ORCHESTRATOR")
    response = ReadinessResponse(
        status="not_ready" if missing else "ready",
        missing=missing,
        providers=provider_states,
    )
    if missing:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )
    return response
