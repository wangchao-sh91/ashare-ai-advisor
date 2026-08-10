from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import HttpUrl, ValidationError

from app.domain import (
    AnswerKind,
    Citation,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    MarketDataCategory,
    NormalizedMarketRecord,
    SourceType,
    StructuredAnswer,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
INSTRUMENT = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def test_instrument_has_exchange_qualified_symbol() -> None:
    assert INSTRUMENT.symbol == "SSE:600519"


def test_normalized_record_serializes_canonical_values() -> None:
    record = NormalizedMarketRecord(
        id="price-1",
        instrument=INSTRUMENT,
        category=MarketDataCategory.PRICE,
        observed_at=date(2026, 8, 6),
        values={"close": Decimal("1420.50")},
        units={"close": "CNY/share"},
        interface="stock_zh_a_hist",
        upstream_source="Eastmoney via AKShare",
        cutoff=NOW,
        retrieved_at=NOW,
    )

    payload = record.model_dump(mode="json")
    assert payload["instrument"]["code"] == "600519"
    assert payload["values"]["close"] == "1420.50"


def test_invalid_record_period_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedMarketRecord(
            id="bad-period",
            instrument=INSTRUMENT,
            category=MarketDataCategory.FINANCIAL,
            observed_at=date(2026, 6, 30),
            values={"revenue": 1},
            interface="financial_abstract",
            upstream_source="provider",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 6, 30),
            cutoff=NOW,
            retrieved_at=NOW,
        )


def test_computed_metric_requires_source_ids() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="return-1",
            kind=EvidenceKind.COMPUTED_METRIC,
            claim="区间收益率",
            value=Decimal("0.1"),
            retrieved_at=NOW,
        )


def test_citation_enforces_provider_locator() -> None:
    with pytest.raises(ValidationError):
        Citation(
            id="web-1",
            source_type=SourceType.WEB,
            title="公告",
            supported_claim="公司发布公告",
            retrieved_at=NOW,
        )

    citation = Citation(
        id="web-1",
        source_type=SourceType.WEB,
        title="公告",
        supported_claim="公司发布公告",
        url=HttpUrl("https://example.com/notice"),
        retrieved_at=NOW,
    )
    assert citation.url is not None


def test_structured_knowledge_answer_allows_research_sections_to_be_empty() -> None:
    answer = StructuredAnswer(
        kind=AnswerKind.KNOWLEDGE,
        summary="市盈率是估值指标。",
        answered_at=NOW,
    )

    assert answer.facts == []
    assert answer.citations == []
    assert "不构成任何投资建议" in answer.disclaimer
