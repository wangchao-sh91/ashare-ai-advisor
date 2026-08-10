"""Process health and secret-safe configuration readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.core.settings import Settings

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "not_ready"]
    missing: list[str]


def _settings_from_request(request: Request) -> Settings:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("application settings are unavailable")
    return settings


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness without touching external providers."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request) -> ReadinessResponse | JSONResponse:
    """Report whether required provider configuration is present."""
    settings = _settings_from_request(request)
    missing = list(settings.missing_required_provider_settings())
    runtime = getattr(request.app.state, "search_runtime", None)
    if settings.doubao_search_auth_configured() and (
        runtime is None or not bool(getattr(runtime, "is_ready", False))
    ):
        missing.append("DOUBAO_SEARCH_MCP")
    if getattr(request.app.state, "orchestrator", None) is None:
        missing.append("ORCHESTRATOR")
    response = ReadinessResponse(
        status="not_ready" if missing else "ready",
        missing=missing,
    )
    if missing:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )
    return response
