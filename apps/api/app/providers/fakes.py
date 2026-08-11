"""Deterministic offline provider fakes for tests and local verification mode."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from langchain_core.messages import BaseMessage
from pydantic import HttpUrl

from app.agent.generation import AnswerDraft
from app.agent.routing import IntentKind, QuestionNormalization
from app.domain import (
    CategoryOutcome,
    CategoryStatus,
    Citation,
    EvidenceCategory,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    NormalizedMarketRecord,
    ProviderKind,
    SourceType,
)

STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)
INDEX = Instrument(
    name="沪深300",
    code="000300",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.BROAD_INDEX,
)


class FakeStructuredModelGateway:
    async def generate_structured(
        self,
        messages: Sequence[BaseMessage],
        schema: type[Any],
    ) -> Any:
        content = str(messages[-1].content)
        if schema is QuestionNormalization:
            return _normalize(content)
        if schema is AnswerDraft:
            payload = json.loads(content)
            return AnswerDraft(
                summary="已基于离线验证证据形成结构化研究回答。",
                fact_ids=payload["allowed_fact_ids"],
                analysis=["事实与解释保持分开，事件与价格仅表述为时序关联。"],
                risks=["市场数据与公开信息均存在时效性和不确定性。"],
                citation_ids=payload["allowed_citation_ids"],
            )
        raise TypeError("unsupported fake structured schema")


class FakeTushareProvider:
    async def outcome(self, **kwargs: object) -> CategoryOutcome:
        instrument = kwargs["instrument"]
        start = kwargs["start_date"]
        end = kwargs["end_date"]
        if (
            not isinstance(instrument, Instrument)
            or not isinstance(start, date)
            or not isinstance(end, date)
        ):
            raise TypeError("invalid fake Tushare request")
        dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        dates = dates[-7:] if len(dates) >= 7 else [start + timedelta(days=i) for i in range(7)]
        now = datetime.now(UTC)
        records = [
            NormalizedMarketRecord(
                id=f"fake:daily:{instrument.ts_code}:{observed.isoformat()}",
                instrument=instrument,
                observed_at=observed,
                values={"close": Decimal(100 + index), "volume": 100000 + index * 1000},
                units={"close": "CNY", "volume": "shares"},
                cutoff=now,
                retrieved_at=now,
            )
            for index, observed in enumerate(dates)
        ]
        evidence = EvidenceItem(
            id="fake:price",
            kind=EvidenceKind.MARKET_FACT,
            category=EvidenceCategory.PRICE_DAILY,
            claim="离线验收模式收盘价",
            value=cast(Decimal, records[-1].values["close"]),
            unit="CNY",
            instrument=instrument,
            source_ids=[records[-1].id],
            cutoff=now,
            retrieved_at=now,
        )
        return CategoryOutcome(
            category=EvidenceCategory.PRICE_DAILY,
            provider=ProviderKind.TUSHARE,
            status=CategoryStatus.SUFFICIENT,
            evidence=[evidence],
            records=records,
        )


class FakeSearchProvider:
    async def outcome(self, request: Any) -> CategoryOutcome:
        now = datetime.now(UTC)
        instrument = request.instrument or INDEX
        citation = Citation(
            id=f"fake:web:{request.category.value}",
            source_type=SourceType.WEB,
            title=f"{instrument.name}{instrument.ts_code}公开资料",
            supported_claim=f"{instrument.name}（{instrument.ts_code}）公开信息已核验。",
            category=request.category,
            publisher="本地验收提供方",
            domain="example.com",
            url=HttpUrl(f"https://example.com/{request.category.value}"),
            published_at=now - timedelta(days=1),
            retrieved_at=now,
        )
        evidence = EvidenceItem(
            id=f"fake:evidence:{request.category.value}",
            kind=EvidenceKind.WEB_FACT,
            category=request.category,
            claim=citation.supported_claim,
            instrument=instrument,
            source_ids=[citation.id],
            cutoff=citation.published_at,
            retrieved_at=now,
        )
        return CategoryOutcome(
            category=request.category,
            provider=ProviderKind.DOUBAO_SEARCH,
            status=CategoryStatus.SUFFICIENT,
            evidence=[evidence],
            citations=[citation],
        )


def _normalize(content: str) -> QuestionNormalization:
    current = content.split("Current question:\n", 1)[-1].split("\n\n", 1)[0]
    if any(term in current for term in ("比较", "基金", "美股", "港股", "保证收益")):
        return QuestionNormalization(
            rewritten_question=current,
            intent=IntentKind.OUT_OF_SCOPE,
            unsupported_reason="超出首版支持范围",
            comparison_requested="比较" in current,
            rationale="离线范围规则",
        )
    if "000001" in current:
        return QuestionNormalization(
            rewritten_question=current,
            intent=IntentKind.SINGLE_STOCK,
            clarification_required=True,
            clarification_question="请明确是上证指数还是平安银行。",
            rationale="代码歧义",
        )
    if "沪深300" in content:
        return QuestionNormalization(
            rewritten_question="分析沪深300当前公开情况",
            intent=IntentKind.BROAD_INDEX,
            instrument=INDEX,
            requested_categories=[EvidenceCategory.INDEX_CONTEXT],
            time_sensitive=True,
            rationale="宽基指数搜索",
        )
    if "贵州茅台" not in content and "它" not in current:
        return QuestionNormalization(
            rewritten_question=current,
            intent=IntentKind.STABLE_KNOWLEDGE,
            rationale="稳定金融知识",
        )
    categories: list[EvidenceCategory] = []
    if any(term in current for term in ("走势", "日线", "价格")):
        categories.append(EvidenceCategory.PRICE_DAILY)
    if "估值" in current:
        categories.append(EvidenceCategory.VALUATION)
    if any(term in current for term in ("公告", "新闻")):
        categories.append(EvidenceCategory.CORPORATE_EVENT)
    if not categories:
        categories.append(EvidenceCategory.PRICE_DAILY)
    return QuestionNormalization(
        rewritten_question=f"分析贵州茅台600519.SH：{current}",
        intent=IntentKind.MIXED if "解释" in current else IntentKind.SINGLE_STOCK,
        instrument=STOCK,
        requested_categories=categories,
        time_sensitive=any(category is not EvidenceCategory.PRICE_DAILY for category in categories),
        rationale="离线规范化",
    )
