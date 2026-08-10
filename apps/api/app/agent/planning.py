"""Deterministic bounded evidence planning over approved application operations."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.routing import IntentClassification, IntentKind
from app.domain import Instrument, InstrumentType, MarketDataCategory
from app.providers.akshare_allowlist import MarketOperation
from app.providers.search_gateway import FreshnessIntent, SearchRequest

MAX_MARKET_CALLS = 6
MAX_SEARCH_CALLS = 1


class MarketCallPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: MarketOperation
    category: MarketDataCategory
    required: bool = True


class EvidencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentKind
    instrument: Instrument | None = None
    market_calls: list[MarketCallPlan] = Field(default_factory=list, max_length=MAX_MARKET_CALLS)
    search_calls: list[SearchRequest] = Field(default_factory=list, max_length=MAX_SEARCH_CALLS)
    unsupported_categories: list[MarketDataCategory] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_instrument_calls(self) -> "EvidencePlan":
        if self.market_calls and self.instrument is None:
            raise ValueError("market calls require a resolved instrument")
        if len({call.category for call in self.market_calls}) != len(self.market_calls):
            raise ValueError("each market category may be planned only once")
        return self


_STOCK_OPERATIONS = {
    MarketDataCategory.PRICE: MarketOperation.STOCK_HISTORY,
    MarketDataCategory.FINANCIAL: MarketOperation.FINANCIAL_OVERVIEW,
    MarketDataCategory.VALUATION: MarketOperation.VALUATION_HISTORY,
    MarketDataCategory.OWNERSHIP: MarketOperation.OWNERSHIP,
    MarketDataCategory.PLEDGE: MarketOperation.PLEDGE,
}


class EvidencePlanner:
    def build(
        self,
        question: str,
        classification: IntentClassification,
        instrument: Instrument | None,
    ) -> EvidencePlan:
        categories = list(classification.requested_categories)
        calls: list[MarketCallPlan] = []
        unsupported: list[MarketDataCategory] = []

        if classification.intent in {
            IntentKind.SINGLE_STOCK,
            IntentKind.BROAD_INDEX,
            IntentKind.MIXED,
        }:
            if instrument is None:
                raise ValueError("research intent requires a resolved instrument")
            if not categories:
                categories = [
                    MarketDataCategory.INDEX_PRICE
                    if instrument.instrument_type is InstrumentType.BROAD_INDEX
                    else MarketDataCategory.PRICE
                ]
            for category in categories[:MAX_MARKET_CALLS]:
                operation = self._operation_for(instrument, category)
                if operation is None:
                    unsupported.append(category)
                else:
                    calls.append(
                        MarketCallPlan(operation=operation, category=category, required=True)
                    )

        searches: list[SearchRequest] = []
        if classification.time_sensitive:
            query = " ".join(question.split())[:100]
            searches.append(
                SearchRequest(
                    query=query,
                    result_limit=5,
                    freshness_intent=FreshnessIntent.MONTH,
                    authority_intent=True,
                )
            )
        return EvidencePlan(
            intent=classification.intent,
            instrument=instrument,
            market_calls=calls,
            search_calls=searches,
            unsupported_categories=unsupported,
        )

    @staticmethod
    def _operation_for(
        instrument: Instrument,
        category: MarketDataCategory,
    ) -> MarketOperation | None:
        if instrument.instrument_type is InstrumentType.BROAD_INDEX:
            if category in {MarketDataCategory.PRICE, MarketDataCategory.INDEX_PRICE}:
                return MarketOperation.INDEX_HISTORY
            return None
        return _STOCK_OPERATIONS.get(category)
