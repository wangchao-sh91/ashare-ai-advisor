"""Runtime composition for real providers and model-reviewed answer generation."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.execution import ConstrainedToolExecutor
from app.agent.generation import AnswerGenerator
from app.agent.orchestrator import ControlledOrchestrator
from app.agent.planning import EvidencePlanner
from app.agent.routing import QuestionNormalizer
from app.core.settings import Settings
from app.providers.fakes import (
    FakeSearchProvider,
    FakeStructuredModelGateway,
    FakeTushareProvider,
)
from app.providers.model_gateway import DeepSeekModelGateway
from app.providers.search_gateway import DoubaoSearchGateway, SearchReadiness
from app.providers.tushare_gateway import TushareGateway


@dataclass(slots=True)
class ProviderRuntime:
    orchestrator: ControlledOrchestrator
    search: DoubaoSearchGateway | None = None

    @property
    def search_readiness(self) -> SearchReadiness:
        return self.search.readiness if self.search else SearchReadiness.USABLE

    async def aclose(self) -> None:
        if self.search is not None:
            await self.search.aclose()


def build_live_runtime(settings: Settings) -> ProviderRuntime:
    model = DeepSeekModelGateway.from_settings(settings)
    price = TushareGateway.from_settings(settings)
    search = DoubaoSearchGateway.from_settings(settings)
    orchestrator = ControlledOrchestrator(
        normalizer=QuestionNormalizer(model),
        planner=EvidencePlanner(search_result_limit=settings.doubao_search_result_count),
        executor=ConstrainedToolExecutor(price_provider=price, search_provider=search),
        generator=AnswerGenerator(model),
    )
    return ProviderRuntime(orchestrator=orchestrator, search=search)


def build_fake_runtime() -> ProviderRuntime:
    model = FakeStructuredModelGateway()
    return ProviderRuntime(
        orchestrator=ControlledOrchestrator(
            normalizer=QuestionNormalizer(model),
            planner=EvidencePlanner(),
            executor=ConstrainedToolExecutor(
                price_provider=FakeTushareProvider(),
                search_provider=FakeSearchProvider(),
            ),
            generator=AnswerGenerator(model),
        )
    )
