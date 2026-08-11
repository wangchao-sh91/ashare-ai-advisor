from datetime import UTC, date, datetime

import pytest
from pydantic import HttpUrl, ValidationError

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
    InsufficiencyReason,
    ProviderKind,
    ProviderPlan,
    SourceType,
    TushareProvenance,
    WebProvenance,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def test_instrument_produces_canonical_tushare_code_and_validates_exchange() -> None:
    assert STOCK.ts_code == "600519.SH"
    with pytest.raises(ValidationError):
        Instrument(
            name="贵州茅台",
            code="600519",
            exchange=Exchange.SZSE,
            instrument_type=InstrumentType.STOCK,
        )


def test_category_plan_outcome_and_provenance_serialize() -> None:
    plan = ProviderPlan(
        category=EvidenceCategory.PRICE_DAILY,
        provider=ProviderKind.TUSHARE,
        instrument=STOCK,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 7),
    )
    evidence = EvidenceItem(
        id="price:1",
        kind=EvidenceKind.MARKET_FACT,
        category=EvidenceCategory.PRICE_DAILY,
        claim="收盘价",
        source_ids=["daily:1"],
        retrieved_at=NOW,
    )
    outcome = CategoryOutcome(
        category=EvidenceCategory.PRICE_DAILY,
        provider=ProviderKind.TUSHARE,
        status=CategoryStatus.SUFFICIENT,
        evidence=[evidence],
    )
    assert plan.model_dump(mode="json")["provider"] == "tushare"
    assert outcome.model_dump(mode="json")["status"] == "sufficient"
    provenance = TushareProvenance(
        ts_code="600519.SH",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 7),
        cutoff=NOW,
        retrieved_at=NOW,
        units={"vol": "shares", "amount": "CNY"},
    )
    web = WebProvenance(
        query="贵州茅台 公告",
        category=EvidenceCategory.CORPORATE_EVENT,
        retrieved_at=NOW,
        result_count=1,
    )
    assert provenance.interface == "pro.daily"
    assert web.result_count == 1


def test_non_sufficient_outcome_requires_reason() -> None:
    with pytest.raises(ValidationError):
        CategoryOutcome(
            category=EvidenceCategory.VALUATION,
            provider=ProviderKind.DOUBAO_SEARCH,
            status=CategoryStatus.INSUFFICIENT,
        )
    valid = CategoryOutcome(
        category=EvidenceCategory.VALUATION,
        provider=ProviderKind.DOUBAO_SEARCH,
        status=CategoryStatus.INSUFFICIENT,
        reason=InsufficiencyReason.NO_RESULTS,
    )
    assert valid.reason is InsufficiencyReason.NO_RESULTS


def test_source_boundaries_are_enforced() -> None:
    with pytest.raises(ValidationError):
        Citation(
            id="web:1",
            source_type=SourceType.WEB,
            title="公告",
            supported_claim="公告事实",
            retrieved_at=NOW,
        )
    citation = Citation(
        id="web:1",
        source_type=SourceType.WEB,
        title="公告",
        supported_claim="公告事实",
        category=EvidenceCategory.CORPORATE_EVENT,
        url=HttpUrl("https://example.com/notice"),
        retrieved_at=NOW,
    )
    assert citation.source_type is SourceType.WEB
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="bad",
            kind=EvidenceKind.MARKET_FACT,
            category=EvidenceCategory.VALUATION,
            claim="搜索估值",
            retrieved_at=NOW,
        )
