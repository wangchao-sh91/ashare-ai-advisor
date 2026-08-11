"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import ChatOrchestrator
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.logging import CorrelationIdMiddleware, configure_logging
from app.core.runtime import ProviderRuntime, build_fake_runtime, build_live_runtime
from app.core.settings import ProviderMode, Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    orchestrator: ChatOrchestrator | None = None,
    provider_runtime: ProviderRuntime | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level.value, runtime_settings.secret_values())

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime = application.state.provider_runtime
        if application.state.orchestrator is None:
            try:
                if runtime is None and runtime_settings.provider_mode is ProviderMode.FAKE:
                    runtime = build_fake_runtime()
                elif runtime is None and not runtime_settings.missing_required_provider_settings():
                    runtime = build_live_runtime(runtime_settings)
                if runtime is not None:
                    application.state.provider_runtime = runtime
                    application.state.orchestrator = runtime.orchestrator
            except Exception:
                logger.error("runtime_orchestrator_initialization_failed")
        try:
            yield
        finally:
            active = application.state.provider_runtime
            if active is not None:
                await active.aclose()

    application = FastAPI(title="A-share AI Advisor API", version="0.1.0", lifespan=lifespan)
    application.state.settings = runtime_settings
    application.state.provider_runtime = provider_runtime
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
