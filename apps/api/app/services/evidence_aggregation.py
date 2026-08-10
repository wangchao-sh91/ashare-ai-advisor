"""Category-level market evidence failure isolation."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import (
    ErrorCode,
    EvidenceItem,
    Limitation,
    LimitationCode,
    MarketDataCategory,
)


class CategoryStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class CategoryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: MarketDataCategory
    status: CategoryStatus
    evidence: list[EvidenceItem] = Field(default_factory=list)
    detail: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_status_payload(self) -> "CategoryOutcome":
        if self.status is CategoryStatus.AVAILABLE and not self.evidence:
            raise ValueError("available category requires evidence")
        if self.status is not CategoryStatus.AVAILABLE and self.evidence:
            raise ValueError("failed category cannot carry evidence")
        if self.status is not CategoryStatus.AVAILABLE and not self.detail:
            raise ValueError("failed category requires a detail")
        return self


class EvidenceAggregation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    unavailable_categories: list[MarketDataCategory] = Field(default_factory=list)
    sufficient: bool
    terminal_error: ErrorCode | None = None


def aggregate_category_evidence(
    outcomes: list[CategoryOutcome],
    *,
    required_categories: set[MarketDataCategory],
) -> EvidenceAggregation:
    """Preserve independent valid categories and stop when required evidence is absent."""
    categories = [outcome.category for outcome in outcomes]
    if len(categories) != len(set(categories)):
        raise ValueError("each market data category may appear only once")

    available = {
        outcome.category for outcome in outcomes if outcome.status is CategoryStatus.AVAILABLE
    }
    evidence = [
        item
        for outcome in outcomes
        if outcome.status is CategoryStatus.AVAILABLE
        for item in outcome.evidence
    ]
    failures = [outcome for outcome in outcomes if outcome.status is not CategoryStatus.AVAILABLE]
    limitations = [
        Limitation(
            code=(
                LimitationCode.DATA_UNAVAILABLE
                if outcome.status is CategoryStatus.UNAVAILABLE
                else LimitationCode.PARTIAL_DATA
            ),
            message=outcome.detail or "market data category unavailable",
            affected_categories=[outcome.category.value],
        )
        for outcome in failures
    ]
    missing_required = required_categories - available
    sufficient = bool(evidence) and not missing_required
    if missing_required and not any(
        set(limitation.affected_categories) & {category.value for category in missing_required}
        for limitation in limitations
    ):
        limitations.append(
            Limitation(
                code=LimitationCode.DATA_UNAVAILABLE,
                message="required market data categories produced no evidence",
                affected_categories=sorted(category.value for category in missing_required),
            )
        )
    return EvidenceAggregation(
        evidence=evidence,
        limitations=limitations,
        unavailable_categories=[outcome.category for outcome in failures],
        sufficient=sufficient,
        terminal_error=None if sufficient else ErrorCode.MARKET_DATA_UNAVAILABLE,
    )
