from datetime import UTC, datetime
from decimal import Decimal

from app.domain import (
    ErrorCode,
    EvidenceItem,
    EvidenceKind,
    LimitationCode,
    MarketDataCategory,
)
from app.services.evidence_aggregation import (
    CategoryOutcome,
    CategoryStatus,
    aggregate_category_evidence,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def evidence(identifier: str) -> EvidenceItem:
    return EvidenceItem(
        id=identifier,
        kind=EvidenceKind.COMPUTED_METRIC,
        claim="validated price trend",
        value=Decimal(10),
        unit="percent",
        formula="deterministic formula",
        source_ids=["source:1"],
        retrieved_at=NOW,
    )


def test_unrelated_category_failure_preserves_valid_required_evidence() -> None:
    result = aggregate_category_evidence(
        [
            CategoryOutcome(
                category=MarketDataCategory.PRICE,
                status=CategoryStatus.AVAILABLE,
                evidence=[evidence("price-return")],
            ),
            CategoryOutcome(
                category=MarketDataCategory.VALUATION,
                status=CategoryStatus.UNAVAILABLE,
                detail="valuation upstream timed out",
            ),
        ],
        required_categories={MarketDataCategory.PRICE},
    )

    assert result.sufficient
    assert result.terminal_error is None
    assert [item.id for item in result.evidence] == ["price-return"]
    assert result.unavailable_categories == [MarketDataCategory.VALUATION]
    assert result.limitations[0].code is LimitationCode.DATA_UNAVAILABLE


def test_invalid_required_category_produces_no_sufficient_evidence_outcome() -> None:
    result = aggregate_category_evidence(
        [
            CategoryOutcome(
                category=MarketDataCategory.PRICE,
                status=CategoryStatus.INVALID,
                detail="price history has incompatible units",
            ),
            CategoryOutcome(
                category=MarketDataCategory.OWNERSHIP,
                status=CategoryStatus.AVAILABLE,
                evidence=[evidence("ownership-fact")],
            ),
        ],
        required_categories={MarketDataCategory.PRICE},
    )

    assert not result.sufficient
    assert result.terminal_error is ErrorCode.MARKET_DATA_UNAVAILABLE
    assert result.limitations[0].code is LimitationCode.PARTIAL_DATA
    assert [item.id for item in result.evidence] == ["ownership-fact"]


def test_empty_results_do_not_authorize_unsupported_analysis() -> None:
    result = aggregate_category_evidence(
        [],
        required_categories={MarketDataCategory.PRICE},
    )

    assert not result.sufficient
    assert result.evidence == []
    assert result.terminal_error is ErrorCode.MARKET_DATA_UNAVAILABLE
    assert result.limitations[0].affected_categories == ["price"]
