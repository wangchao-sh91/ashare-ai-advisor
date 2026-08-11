"""Provider-independent domain models for category-grounded research."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

INVESTMENT_DISCLAIMER = "本回答仅供研究参考，不构成任何投资建议。投资有风险，决策需谨慎。"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentType(StrEnum):
    STOCK = "stock"
    BROAD_INDEX = "broad_index"


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"


_TS_SUFFIX = {Exchange.SSE: "SH", Exchange.SZSE: "SZ", Exchange.BSE: "BJ"}


class Instrument(DomainModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r"^\d{6}$")
    exchange: Exchange
    instrument_type: InstrumentType

    @model_validator(mode="after")
    def validate_stock_exchange(self) -> Self:
        if self.instrument_type is InstrumentType.STOCK:
            expected = (
                Exchange.SSE
                if self.code.startswith("6")
                else Exchange.BSE
                if self.code.startswith(("4", "8"))
                else Exchange.SZSE
            )
            if self.exchange is not expected:
                raise ValueError("stock code and exchange are inconsistent")
        return self

    @property
    def symbol(self) -> str:
        return f"{self.exchange.value}:{self.code}"

    @property
    def ts_code(self) -> str:
        return f"{self.code}.{_TS_SUFFIX[self.exchange]}"


class EvidenceCategory(StrEnum):
    PRICE_DAILY = "price_daily"
    FINANCIAL = "financial"
    VALUATION = "valuation"
    OWNERSHIP = "ownership"
    PLEDGE = "pledge"
    CORPORATE_EVENT = "corporate_event"
    INDEX_CONTEXT = "index_context"


MarketDataCategory = EvidenceCategory
MarketValue = Decimal | int | str | date | None


class NormalizedMarketRecord(DomainModel):
    id: str = Field(min_length=1, max_length=128)
    instrument: Instrument
    category: EvidenceCategory = EvidenceCategory.PRICE_DAILY
    observed_at: date
    values: dict[str, MarketValue] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)
    interface: str = Field(default="pro.daily", min_length=1, max_length=128)
    upstream_source: str = Field(default="Tushare", min_length=1, max_length=200)
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
    TIMING_UNCERTAIN = "timing_uncertain"


class QualityFlag(DomainModel):
    code: QualityFlagCode
    detail: str = Field(min_length=1, max_length=500)


class SourceType(StrEnum):
    TUSHARE = "tushare"
    WEB = "web"


class SourceQuality(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Citation(DomainModel):
    id: str = Field(min_length=1, max_length=128)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=300)
    supported_claim: str = Field(min_length=1, max_length=1000)
    category: EvidenceCategory | None = None
    source_quality: SourceQuality = SourceQuality.PRIMARY
    interface: str | None = Field(default=None, max_length=128)
    publisher: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=253)
    url: HttpUrl | None = None
    snippet: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    retrieved_at: datetime
    authority_level: int | None = Field(default=None, ge=0, le=10)
    authority_description: str | None = Field(default=None, max_length=300)
    query: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_source_locator(self) -> Self:
        if self.source_type is SourceType.WEB and self.url is None:
            raise ValueError("web citations require an HTTP(S) URL")
        if self.source_type is SourceType.TUSHARE and self.interface is None:
            raise ValueError("Tushare citations require an interface name")
        return self


class EvidenceItem(DomainModel):
    id: str = Field(min_length=1, max_length=128)
    kind: EvidenceKind
    category: EvidenceCategory | None = None
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
        if self.kind is EvidenceKind.MARKET_FACT and self.category not in {
            None,
            EvidenceCategory.PRICE_DAILY,
        }:
            raise ValueError("only daily prices may be market facts")
        return self


class ProviderKind(StrEnum):
    TUSHARE = "tushare"
    DOUBAO_SEARCH = "doubao_search"


class CategoryStatus(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class InsufficiencyReason(StrEnum):
    NO_RESULTS = "no_results"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_SCHEMA = "invalid_schema"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED = "unsupported"
    CATEGORY_MISMATCH = "category_mismatch"


class ProviderPlan(DomainModel):
    category: EvidenceCategory
    provider: ProviderKind
    required: bool = True
    instrument: Instrument | None = None
    start_date: date | None = None
    end_date: date | None = None
    query: str | None = Field(default=None, max_length=100)
    result_limit: int = Field(default=5, ge=1, le=50)


class CategoryOutcome(DomainModel):
    category: EvidenceCategory
    provider: ProviderKind
    status: CategoryStatus
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    records: list[NormalizedMarketRecord] = Field(default_factory=list)
    reason: InsufficiencyReason | None = None
    detail: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.status is CategoryStatus.SUFFICIENT and not (self.evidence or self.citations):
            raise ValueError("sufficient category requires evidence or citations")
        if self.status is not CategoryStatus.SUFFICIENT and self.reason is None:
            raise ValueError("non-sufficient category requires a reason")
        if self.status is not CategoryStatus.SUFFICIENT and self.records:
            raise ValueError("non-sufficient category cannot carry market records")
        return self


class TushareProvenance(DomainModel):
    interface: str = "pro.daily"
    ts_code: str = Field(pattern=r"^\d{6}\.(SH|SZ|BJ)$")
    period_start: date
    period_end: date
    cutoff: datetime
    retrieved_at: datetime
    units: dict[str, str]


class WebProvenance(DomainModel):
    query: str = Field(min_length=1, max_length=100)
    category: EvidenceCategory
    retrieved_at: datetime
    result_count: int = Field(ge=0, le=50)


class LimitationCode(StrEnum):
    DATA_UNAVAILABLE = "data_unavailable"
    DATA_STALE = "data_stale"
    PARTIAL_DATA = "partial_data"
    SEARCH_UNVERIFIED = "search_unverified"
    SOURCE_CONFLICT = "source_conflict"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    QUOTA_EXHAUSTED = "quota_exhausted"


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
