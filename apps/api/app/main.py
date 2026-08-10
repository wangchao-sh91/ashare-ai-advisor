"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Protocol

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import ChatOrchestrator
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.logging import CorrelationIdMiddleware, configure_logging
from app.core.runtime import VerificationOrchestrator, build_live_orchestrator
from app.core.settings import ProviderMode, Settings, get_settings
from app.providers.doubao_mcp import DoubaoMcpRuntime, McpRuntimeError, StdioDoubaoConnector

logger = logging.getLogger(__name__)


class SearchRuntime(Protocol):
    @property
    def is_ready(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


def _default_search_runtime(settings: Settings) -> SearchRuntime | None:
    if not settings.doubao_search_auth_configured():
        return None
    try:
        return DoubaoMcpRuntime(
            connector=StdioDoubaoConnector(settings.doubao_search_child_env()),
            timeout_seconds=settings.doubao_search_timeout_seconds,
            max_retries=settings.doubao_search_max_retries,
        )
    except McpRuntimeError:
        return None


def create_app(
    settings: Settings | None = None,
    *,
    search_runtime: SearchRuntime | None = None,
    orchestrator: ChatOrchestrator | None = None,
) -> FastAPI:
    """Create the API application."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level.value, runtime_settings.secret_values())

    runtime = search_runtime or _default_search_runtime(runtime_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_runtime: SearchRuntime | None = application.state.search_runtime
        if active_runtime is not None:
            with suppress(McpRuntimeError):
                await active_runtime.start()
        if application.state.orchestrator is None:
            if runtime_settings.provider_mode is ProviderMode.FAKE:
                application.state.orchestrator = VerificationOrchestrator()
            elif not runtime_settings.missing_required_provider_settings():
                try:
                    application.state.orchestrator = await build_live_orchestrator(
                        runtime_settings,
                        active_runtime,
                    )
                except Exception:
                    logger.error("runtime_orchestrator_initialization_failed")
        try:
            yield
        finally:
            if active_runtime is not None:
                await active_runtime.stop()

    application = FastAPI(title="A-share AI Advisor API", version="0.1.0", lifespan=lifespan)
    application.state.settings = runtime_settings
    application.state.search_runtime = runtime
    application.state.orchestrator = orchestrator
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in runtime_settings.cors_allowed_origins],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health_router)
    application.include_router(chat_router)
    return application


app = create_app()
