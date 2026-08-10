"""Runtime composition for real providers and deterministic verification mode."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import HttpUrl

from app.agent.entity_resolution import (
    ContextualEntityResolver,
    EntityResolution,
    EntitySource,
    EntityStatus,
)
from app.agent.execution import ConstrainedToolExecutor
from app.agent.generation import AnswerGenerator
from app.agent.orchestrator import (
    ControlledOrchestrator,
    OrchestrationResult,
    OrchestrationStage,
    OrchestrationStatus,
    ProgressCallback,
)
from app.agent.planning import EvidencePlanner
from app.agent.routing import IntentClassifier
from app.api.chat_models import ChatRequest
from app.core.settings import Settings
from app.domain import (
    INVESTMENT_DISCLAIMER,
    AnswerKind,
    Citation,
    ErrorCode,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    SourceType,
    StructuredAnswer,
)
from app.providers.akshare_allowlist import MarketOperation
from app.providers.akshare_gateway import AKShareGateway
from app.providers.model_gateway import DeepSeekModelGateway
from app.providers.search_gateway import DoubaoSearchGateway
from app.services.instrument_resolver import InstrumentResolver
from app.services.live_market import LiveMarketEvidenceTool
from app.services.ttl_cache import TTLCache


async def build_live_orchestrator(
    settings: Settings,
    search_runtime: Any,
) -> ControlledOrchestrator:
    """Build the production workflow after obtaining the current stock catalog."""
    gateway = AKShareGateway(
        timeout_seconds=settings.akshare_timeout_seconds,
        max_retries=settings.akshare_max_retries,
        max_workers=settings.akshare_max_workers,
        cache=TTLCache(settings.market_data_cache_ttl_seconds),
    )
    catalog = await gateway.fetch(MarketOperation.STOCK_CATALOG)
    model = DeepSeekModelGateway.from_settings(settings)
    search = DoubaoSearchGateway(search_runtime) if search_runtime is not None else None
    return ControlledOrchestrator(
        classifier=IntentClassifier(model),
        entity_resolver=ContextualEntityResolver(InstrumentResolver(catalog)),
        planner=EvidencePlanner(),
        executor=ConstrainedToolExecutor(
            market_tool=LiveMarketEvidenceTool(gateway),
            search_tool=search,
        ),
        generator=AnswerGenerator(model),
    )


class VerificationOrchestrator:
    """Deterministic, credential-free runtime used only by deployment checks."""

    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        question = request.question
        await _progress(progress, OrchestrationStage.ROUTING)
        if any(term in question for term in ("比较", "基金", "美股", "港股", "保证收益")):
            return OrchestrationResult(
                status=OrchestrationStatus.REFUSED,
                message="该请求超出首版单一 A 股或宽基指数研究范围。",
                error_code=ErrorCode.UNSUPPORTED_SCOPE,
            )
        if "000001" in question:
            return OrchestrationResult(
                status=OrchestrationStatus.CLARIFICATION_REQUIRED,
                message="请明确是上证指数还是平安银行。",
                error_code=ErrorCode.AMBIGUOUS_INSTRUMENT,
            )

        instrument = _fake_instrument(question, request)
        knowledge = "什么是" in question or "解释" in question and instrument is None
        current = any(term in question for term in ("最新", "最近", "公告", "当前"))
        if instrument is not None:
            await _progress(progress, OrchestrationStage.MARKET_DATA)
        if current:
            await _progress(progress, OrchestrationStage.WEB_SEARCH)
        await _progress(progress, OrchestrationStage.GENERATION)

        now = datetime.now(UTC)
        fact = (
            EvidenceItem(
                id="fake:market:fact",
                kind=EvidenceKind.MARKET_FACT,
                claim="验收模式下的确定性市场数据",
                value=Decimal("100.00"),
                unit="CNY",
                instrument=instrument,
                source_ids=["fake:akshare"],
                cutoff=now,
                retrieved_at=now,
            )
            if instrument is not None
            else None
        )
        citation = (
            Citation(
                id="fake:web:notice",
                source_type=SourceType.WEB,
                title="验收模式公开公告",
                supported_claim="用于验证搜索引用和安全外链渲染。",
                publisher="本地验收提供方",
                domain="example.com",
                url=HttpUrl("https://example.com/notice"),
                retrieved_at=now,
            )
            if current
            else None
        )
        answer = StructuredAnswer(
            kind=AnswerKind.KNOWLEDGE if knowledge else AnswerKind.RESEARCH,
            summary=(
                "市盈率用于比较价格与每股收益，需结合增长和会计口径理解。"
                if knowledge
                else "已完成本地验收模式的结构化研究回答。"
            ),
            facts=[fact] if fact else [],
            analysis=["事实与解释保持分开展示。"],
            risks=[] if knowledge else ["市场数据和模型结论均存在不确定性。"],
            citations=[citation] if citation else [],
            data_cutoff=now if fact else None,
            answered_at=now,
            disclaimer=INVESTMENT_DISCLAIMER,
        )
        entity = (
            EntityResolution(
                status=EntityStatus.RESOLVED,
                instrument=instrument,
                candidates=[instrument],
                source=EntitySource.CURRENT_QUESTION,
            )
            if instrument
            else EntityResolution(status=EntityStatus.NOT_REQUIRED)
        )
        await _progress(progress, OrchestrationStage.VERIFICATION)
        return OrchestrationResult(
            status=OrchestrationStatus.ANSWERED,
            answer=answer,
            entity=entity,
        )


def _fake_instrument(question: str, request: ChatRequest) -> Instrument | None:
    context = " ".join(message.content for message in request.messages)
    combined = f"{question} {context}"
    if "沪深300" in combined:
        return Instrument(
            name="沪深300",
            code="000300",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        )
    if "贵州茅台" in combined or "它" in question:
        return Instrument(
            name="贵州茅台",
            code="600519",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.STOCK,
        )
    return None


async def _progress(
    callback: ProgressCallback | None,
    stage: OrchestrationStage,
) -> None:
    if callback is not None:
        await callback(stage)
        # Keep fake-provider progress observable through the reverse proxy so
        # deployment checks can prove that SSE frames are not buffered.
        await asyncio.sleep(0.05)
