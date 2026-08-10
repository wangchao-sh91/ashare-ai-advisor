"""Provider-independent domain models for grounded research answers."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

INVESTMENT_DISCLAIMER = "本回答仅供研究参考，不构成任何投资建议。投资有风险，决策需谨慎。"


class DomainModel(BaseModel):
    """Strict immutable base for values crossing application boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentType(StrEnum):
    STOCK = "stock"
    BROAD_INDEX = "broad_index"


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"


class Instrument(DomainModel):
    """Canonical identity for a supported stock or broad index."""

    name: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r"^\d{6}$")
    exchange: Exchange
    instrument_type: InstrumentType

    @property
    def symbol(self) -> str:
        """Return a stable exchange-qualified symbol."""
        return f"{self.exchange.value}:{self.code}"


class MarketDataCategory(StrEnum):
    PRICE = "price"
    INDEX_PRICE = "index_price"
    FINANCIAL = "financial"
    VALUATION = "valuation"
    OWNERSHIP = "ownership"
    PLEDGE = "pledge"


MarketValue = Decimal | int | str | date | None


class NormalizedMarketRecord(DomainModel):
    """Canonical market record with provider provenance kept at the edge."""

    id: str = Field(min_length=1, max_length=128)
    instrument: Instrument
    category: MarketDataCategory
    observed_at: date
    values: dict[str, MarketValue] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)
    interface: str = Field(min_length=1, max_length=128)
    upstream_source: str = Field(min_length=1, max_length=200)
    period_start: date | None = None
    period_end: date | None = None
    cutoff: datetime
    retrieved_at: datetime

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class EvidenceKind(StrEnum):
    MARKET_FACT = "market_fact"
    COMPUTED_METRIC = "computed_metric"
    WEB_FACT = "web_fact"


class QualityFlagCode(StrEnum):
    STALE = "stale"
    PARTIAL_COVERAGE = "partial_coverage"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    UNIT_UNCERTAIN = "unit_uncertain"
    SOURCE_CONFLICT = "source_conflict"


class QualityFlag(DomainModel):
    code: QualityFlagCode
    detail: str = Field(min_length=1, max_length=500)


class SourceType(StrEnum):
    AKSHARE = "akshare"
    WEB = "web"


class SourceQuality(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Citation(DomainModel):
    """User-visible attribution for a market or web claim."""

    id: str = Field(min_length=1, max_length=128)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=300)
    supported_claim: str = Field(min_length=1, max_length=1000)
    source_quality: SourceQuality = SourceQuality.PRIMARY
    interface: str | None = Field(default=None, max_length=128)
    publisher: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=253)
    url: HttpUrl | None = None
    snippet: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    retrieved_at: datetime

    @model_validator(mode="after")
    def require_source_locator(self) -> Self:
        if self.source_type is SourceType.WEB and self.url is None:
            raise ValueError("web citations require an HTTP(S) URL")
        if self.source_type is SourceType.AKSHARE and self.interface is None:
            raise ValueError("AKShare citations require an interface name")
        return self


class EvidenceItem(DomainModel):
    """A fact or metric that can be referenced during answer generation."""

    id: str = Field(min_length=1, max_length=128)
    kind: EvidenceKind
    claim: str = Field(min_length=1, max_length=2000)
    value: Decimal | str | None = None
    unit: str | None = Field(default=None, max_length=50)
    instrument: Instrument | None = None
    period_start: date | None = None
    period_end: date | None = None
    formula: str | None = Field(default=None, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    cutoff: datetime | None = None
    retrieved_at: datetime
    quality_flags: list[QualityFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_period_and_sources(self) -> Self:
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        if self.kind is EvidenceKind.COMPUTED_METRIC and not self.source_ids:
            raise ValueError("computed metrics require at least one input source ID")
        return self


class LimitationCode(StrEnum):
    DATA_UNAVAILABLE = "data_unavailable"
    DATA_STALE = "data_stale"
    PARTIAL_DATA = "partial_data"
    SEARCH_UNVERIFIED = "search_unverified"
    SOURCE_CONFLICT = "source_conflict"
    UNSUPPORTED_CATEGORY = "unsupported_category"


class Limitation(DomainModel):
    code: LimitationCode
    message: str = Field(min_length=1, max_length=1000)
    affected_categories: list[str] = Field(default_factory=list, max_length=20)
    recoverable: bool = True


class AnswerKind(StrEnum):
    RESEARCH = "research"
    KNOWLEDGE = "knowledge"
    MIXED = "mixed"
    CLARIFICATION = "clarification"


class StructuredAnswer(DomainModel):
    """Verified semantic answer returned by orchestration."""

    kind: AnswerKind
    summary: str = Field(min_length=1, max_length=4000)
    facts: list[EvidenceItem] = Field(default_factory=list, max_length=100)
    analysis: list[str] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=50)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
    data_cutoff: datetime | None = None
    answered_at: datetime
    disclaimer: str = Field(default=INVESTMENT_DISCLAIMER, min_length=1, max_length=500)
    limitations: list[Limitation] = Field(default_factory=list, max_length=50)


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    CONTEXT_TOO_LARGE = "context_too_large"
    AMBIGUOUS_INSTRUMENT = "ambiguous_instrument"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    MARKET_DATA_UNAVAILABLE = "market_data_unavailable"
    SEARCH_UNAVAILABLE = "search_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    VALIDATION_FAILED = "validation_failed"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"
