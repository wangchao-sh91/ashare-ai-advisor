"""Deterministic category-to-provider evidence planning."""

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.routing import IntentKind, QuestionNormalization
from app.domain import (
    EvidenceCategory,
    Instrument,
    InstrumentType,
    ProviderKind,
    ProviderPlan,
)

MAX_PROVIDER_CALLS = 7

_SEARCH_TERMS = {
    EvidenceCategory.FINANCIAL: "财务 报告 官方",
    EvidenceCategory.VALUATION: "估值 市盈率 市净率 官方",
    EvidenceCategory.OWNERSHIP: "股东 持股 公告",
    EvidenceCategory.PLEDGE: "股份 质押 公告",
    EvidenceCategory.CORPORATE_EVENT: "最新公告 官方",
    EvidenceCategory.INDEX_CONTEXT: "最新情况 指数公司 权威",
}


class EvidencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentKind
    instrument: Instrument | None = None
    calls: list[ProviderPlan] = Field(default_factory=list, max_length=MAX_PROVIDER_CALLS)

    @model_validator(mode="after")
    def validate_unique_categories(self) -> "EvidencePlan":
        categories = [call.category for call in self.calls]
        if len(categories) != len(set(categories)):
            raise ValueError("each evidence category may be planned only once")
        if self.calls and self.instrument is None:
            raise ValueError("provider calls require a canonical instrument")
        return self

    @property
    def market_calls(self) -> list[ProviderPlan]:
        return [call for call in self.calls if call.provider is ProviderKind.TUSHARE]

    @property
    def search_calls(self) -> list[ProviderPlan]:
        return [call for call in self.calls if call.provider is ProviderKind.DOUBAO_SEARCH]


class EvidencePlanner:
    def __init__(self, *, today: date | None = None, search_result_limit: int = 5) -> None:
        self._today = today
        self._search_result_limit = search_result_limit

    def build(self, normalization: QuestionNormalization) -> EvidencePlan:
        if normalization.intent in {IntentKind.STABLE_KNOWLEDGE, IntentKind.OUT_OF_SCOPE}:
            return EvidencePlan(intent=normalization.intent)
        instrument = normalization.instrument
        if instrument is None:
            raise ValueError("research normalization requires a canonical instrument")
        today = self._today or date.today()
        start = normalization.analysis_start or today - timedelta(days=370)
        end = normalization.analysis_end or today
        categories = list(normalization.requested_categories)
        if not categories:
            categories = [
                EvidenceCategory.INDEX_CONTEXT
                if instrument.instrument_type is InstrumentType.BROAD_INDEX
                else EvidenceCategory.PRICE_DAILY
            ]
        calls: list[ProviderPlan] = []
        for category in categories:
            if category is EvidenceCategory.PRICE_DAILY:
                if instrument.instrument_type is not InstrumentType.STOCK:
                    raise ValueError("broad indexes cannot request structured daily prices")
                calls.append(
                    ProviderPlan(
                        category=category,
                        provider=ProviderKind.TUSHARE,
                        instrument=instrument,
                        start_date=start,
                        end_date=end,
                    )
                )
                continue
            query = _search_query(instrument, category)
            calls.append(
                ProviderPlan(
                    category=category,
                    provider=ProviderKind.DOUBAO_SEARCH,
                    instrument=instrument,
                    start_date=start,
                    end_date=end,
                    query=query,
                    result_limit=self._search_result_limit,
                )
            )
        return EvidencePlan(intent=normalization.intent, instrument=instrument, calls=calls)


def _search_query(instrument: Instrument, category: EvidenceCategory) -> str:
    terms = _SEARCH_TERMS.get(category)
    if terms is None:
        raise ValueError("category has no approved search mapping")
    identifier = instrument.ts_code
    if category is EvidenceCategory.CORPORATE_EVENT:
        identifier = instrument.code
    return " ".join(f"{instrument.name} {identifier} {terms}".split())[:100]
