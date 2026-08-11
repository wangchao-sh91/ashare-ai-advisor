"""Typed, bounded Doubao Search Custom HTTPS gateway."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from anyio import sleep
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError

from app.core.settings import DOUBAO_SEARCH_ENDPOINT
from app.domain import (
    CategoryOutcome,
    CategoryStatus,
    Citation,
    EvidenceCategory,
    EvidenceItem,
    EvidenceKind,
    Instrument,
    InsufficiencyReason,
    ProviderKind,
    SourceQuality,
    SourceType,
)
from app.services.event_timeline import deduplicate_event_citations
from app.services.ttl_cache import TTLCache

MAX_SEARCH_TEXT = 2000
MAX_SUPPORTED_CLAIM_TEXT = 1000
SEARCH_SCHEMA_VERSION = "doubao-web-v1"


class FreshnessIntent(StrEnum):
    ANY = "any"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


FRESHNESS_TIME_RANGE = {
    FreshnessIntent.DAY: "OneDay",
    FreshnessIntent.WEEK: "OneWeek",
    FreshnessIntent.MONTH: "OneMonth",
    FreshnessIntent.YEAR: "OneYear",
}


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=100)
    category: EvidenceCategory
    instrument: Instrument | None = None
    result_limit: int = Field(default=5, ge=1, le=50)
    freshness_intent: FreshnessIntent = FreshnessIntent.ANY
    start_date: date | None = None
    end_date: date | None = None
    authority_intent: bool = True


class SearchErrorCode(StrEnum):
    TIMEOUT = "search_timeout"
    UNAVAILABLE = "search_unavailable"
    INVALID_RESPONSE = "search_invalid_response"
    UPSTREAM_ERROR = "search_upstream_error"
    QUOTA_EXHAUSTED = "search_quota_exhausted"
    RATE_LIMITED = "search_rate_limited"


class SearchReadiness(StrEnum):
    CONFIGURED = "configured"
    USABLE = "usable"
    RATE_LIMITED = "rate_limited"
    QUOTA_UNAVAILABLE = "quota_unavailable"
    UNAVAILABLE = "unavailable"


class SearchGatewayError(RuntimeError):
    def __init__(self, code: SearchErrorCode) -> None:
        self.code = code
        super().__init__(f"search request failed with {code.value}")


class ProviderSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider_id: str = Field(alias="Id")
    title: str = Field(alias="Title", min_length=1, max_length=300)
    snippet: str = Field(alias="Snippet", default="")
    site_name: str | None = Field(alias="SiteName", default=None)
    url: HttpUrl = Field(alias="Url")
    summary: str | None = Field(alias="Summary", default=None)
    publish_time: datetime | None = Field(alias="PublishTime", default=None)
    rank_score: float | None = Field(alias="RankScore", default=None)
    authority_description: str | None = Field(alias="AuthInfoDes", default=None)
    authority_level: int | None = Field(alias="AuthInfoLevel", default=None)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: Citation
    category: EvidenceCategory
    snippet: str = Field(max_length=MAX_SEARCH_TEXT)
    relevance_score: float | None = None


class DoubaoSearchGateway:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        timeout_seconds: float = 20,
        max_retries: int = 2,
        max_concurrency: int = 4,
        caches: dict[EvidenceCategory, TTLCache[tuple[Any, ...], list[SearchResult]]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._caches = caches or {}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(
                max_connections=max_concurrency,
                max_keepalive_connections=max_concurrency,
            ),
        )
        self._readiness = SearchReadiness.CONFIGURED

    @classmethod
    def from_settings(cls, settings: Any) -> DoubaoSearchGateway:
        if settings.doubao_search_api_key is None:
            raise ValueError("Doubao Search provider configuration is incomplete")
        capacities = settings.provider_cache_max_entries
        return cls(
            api_key=settings.doubao_search_api_key,
            timeout_seconds=settings.doubao_search_timeout_seconds,
            max_retries=settings.doubao_search_max_retries,
            max_concurrency=settings.doubao_search_max_concurrency,
            caches={
                EvidenceCategory.CORPORATE_EVENT: TTLCache(
                    settings.corporate_event_cache_ttl_seconds, max_entries=capacities
                ),
                EvidenceCategory.INDEX_CONTEXT: TTLCache(
                    settings.index_search_cache_ttl_seconds, max_entries=capacities
                ),
                **{
                    category: TTLCache(
                        settings.financial_search_cache_ttl_seconds,
                        max_entries=capacities,
                    )
                    for category in (
                        EvidenceCategory.FINANCIAL,
                        EvidenceCategory.VALUATION,
                        EvidenceCategory.OWNERSHIP,
                        EvidenceCategory.PLEDGE,
                    )
                },
            },
        )

    @property
    def readiness(self) -> SearchReadiness:
        return self._readiness

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        if request.category is EvidenceCategory.PRICE_DAILY:
            raise ValueError("search cannot satisfy the price_daily category")
        key = (
            SEARCH_SCHEMA_VERSION,
            " ".join(request.query.lower().split()),
            request.category.value,
            request.freshness_intent.value,
            request.start_date,
            request.end_date,
            request.authority_intent,
            request.result_limit,
        )
        cache = self._caches.get(request.category)
        if cache is not None and (cached := cache.get(key)) is not None:
            return cached

        payload = _request_payload(request)
        for attempt in range(self._max_retries + 1):
            try:
                async with self._semaphore:
                    response = await self._client.post(
                        DOUBAO_SEARCH_ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                results = _response_results(response, request)
                self._readiness = SearchReadiness.USABLE
                if cache is not None:
                    cache.set(key, results)
                return results
            except httpx.TimeoutException as exc:
                code = SearchErrorCode.TIMEOUT
                cause: BaseException = exc
            except httpx.RequestError as exc:
                code = SearchErrorCode.UNAVAILABLE
                cause = exc
            except SearchGatewayError as exc:
                code = exc.code
                cause = exc

            if code is SearchErrorCode.QUOTA_EXHAUSTED:
                self._readiness = SearchReadiness.QUOTA_UNAVAILABLE
                raise SearchGatewayError(code) from cause
            retryable = code in {
                SearchErrorCode.TIMEOUT,
                SearchErrorCode.UNAVAILABLE,
                SearchErrorCode.UPSTREAM_ERROR,
                SearchErrorCode.RATE_LIMITED,
            }
            if attempt == self._max_retries or not retryable:
                self._readiness = (
                    SearchReadiness.RATE_LIMITED
                    if code is SearchErrorCode.RATE_LIMITED
                    else SearchReadiness.UNAVAILABLE
                )
                raise SearchGatewayError(code) from cause
            await sleep(min(0.1 * (2**attempt), 1.0))
        raise AssertionError("unreachable")

    async def outcome(self, request: SearchRequest) -> CategoryOutcome:
        try:
            results = await self.search(request)
        except SearchGatewayError as exc:
            reason = {
                SearchErrorCode.QUOTA_EXHAUSTED: InsufficiencyReason.QUOTA_EXHAUSTED,
                SearchErrorCode.RATE_LIMITED: InsufficiencyReason.RATE_LIMITED,
                SearchErrorCode.INVALID_RESPONSE: InsufficiencyReason.INVALID_SCHEMA,
            }.get(exc.code, InsufficiencyReason.PROVIDER_UNAVAILABLE)
            return CategoryOutcome(
                category=request.category,
                provider=ProviderKind.DOUBAO_SEARCH,
                status=CategoryStatus.UNAVAILABLE,
                reason=reason,
                detail="当前公开信息未能通过豆包搜索核验。",
            )
        if not results:
            return CategoryOutcome(
                category=request.category,
                provider=ProviderKind.DOUBAO_SEARCH,
                status=CategoryStatus.INSUFFICIENT,
                reason=InsufficiencyReason.NO_RESULTS,
                detail="未找到足够可靠且与请求类别匹配的公开信息。",
            )
        citations = [result.citation for result in results]
        if request.category is EvidenceCategory.CORPORATE_EVENT:
            citations = deduplicate_event_citations(citations)
            accepted = {item.id for item in citations}
            results = [item for item in results if item.citation.id in accepted]
        evidence = [
            EvidenceItem(
                id=f"evidence:{item.citation.id}",
                kind=EvidenceKind.WEB_FACT,
                category=request.category,
                claim=item.snippet,
                instrument=request.instrument,
                source_ids=[item.citation.id],
                cutoff=item.citation.published_at or item.citation.retrieved_at,
                retrieved_at=item.citation.retrieved_at,
            )
            for item in results
        ]
        return CategoryOutcome(
            category=request.category,
            provider=ProviderKind.DOUBAO_SEARCH,
            status=CategoryStatus.SUFFICIENT,
            evidence=evidence,
            citations=citations,
        )


def _request_payload(request: SearchRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "Query": request.query.strip(),
        "SearchType": "web",
        "Count": request.result_limit,
        "Filter": {"NeedUrl": True, "AuthInfoLevel": 1 if request.authority_intent else 0},
        "QueryControl": {"QueryRewrite": False},
        "Industry": "finance",
    }
    if request.start_date and request.end_date:
        payload["TimeRange"] = _bounded_time_range(request.start_date, request.end_date)
    elif time_range := FRESHNESS_TIME_RANGE.get(request.freshness_intent):
        payload["TimeRange"] = time_range
    return payload


def _bounded_time_range(start_date: date, end_date: date) -> str:
    days = (end_date - start_date).days
    if days <= 1:
        return FRESHNESS_TIME_RANGE[FreshnessIntent.DAY]
    if days <= 7:
        return FRESHNESS_TIME_RANGE[FreshnessIntent.WEEK]
    if days <= 31:
        return FRESHNESS_TIME_RANGE[FreshnessIntent.MONTH]
    return FRESHNESS_TIME_RANGE[FreshnessIntent.YEAR]


def _response_results(response: httpx.Response, request: SearchRequest) -> list[SearchResult]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE) from exc
    if not isinstance(payload, dict):
        raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE)
    error = _provider_error(payload)
    if error == "10406":
        raise SearchGatewayError(SearchErrorCode.QUOTA_EXHAUSTED)
    if error == "700429" or response.status_code == 429:
        raise SearchGatewayError(SearchErrorCode.RATE_LIMITED)
    if error or response.status_code >= 500:
        raise SearchGatewayError(SearchErrorCode.UPSTREAM_ERROR)
    if response.status_code >= 400:
        raise SearchGatewayError(SearchErrorCode.UNAVAILABLE)
    result = payload.get("Result")
    if not isinstance(result, dict) or not isinstance(result.get("WebResults"), list):
        raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE)
    raw_results = result["WebResults"]
    retrieved_at = datetime.now(UTC)
    normalized: list[SearchResult] = []
    for raw in raw_results:
        try:
            parsed = ProviderSearchResult.model_validate(raw)
            item = _normalize(parsed, request, retrieved_at)
            if _matches_category(item, request):
                normalized.append(item)
        except (ValidationError, ValueError):
            continue
    if raw_results and not normalized and request.category is not EvidenceCategory.CORPORATE_EVENT:
        raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE)
    return normalized


def _provider_error(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("ResponseMetadata")
    error = metadata.get("Error") if isinstance(metadata, dict) else None
    if isinstance(error, dict):
        code = error.get("Code") or error.get("code")
        return str(code) if code is not None else "unknown"
    direct = payload.get("Code") or payload.get("code")
    return str(direct) if direct is not None else None


def _normalize(
    result: ProviderSearchResult,
    request: SearchRequest,
    retrieved_at: datetime,
) -> SearchResult:
    parsed = urlsplit(str(result.url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid citation URL")
    text = (result.summary or result.snippet).strip()[:MAX_SEARCH_TEXT]
    if not text:
        raise ValueError("search result has no bounded evidence text")
    supported_claim = text[:MAX_SUPPORTED_CLAIM_TEXT]
    canonical_url = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))
    citation_id = "web:" + sha256(canonical_url.encode()).hexdigest()[:24]
    return SearchResult(
        citation=Citation(
            id=citation_id,
            source_type=SourceType.WEB,
            title=result.title.strip(),
            supported_claim=supported_claim,
            category=request.category,
            snippet=text,
            source_quality=(
                SourceQuality.PRIMARY
                if (result.authority_level or 0) >= 1
                else SourceQuality.SECONDARY
            ),
            publisher=result.site_name.strip() if result.site_name else parsed.hostname,
            domain=parsed.hostname.lower(),
            url=HttpUrl(canonical_url),
            published_at=result.publish_time,
            retrieved_at=retrieved_at,
            authority_level=result.authority_level,
            authority_description=result.authority_description,
            query=request.query,
        ),
        category=request.category,
        snippet=text,
        relevance_score=result.rank_score,
    )


def _matches_category(result: SearchResult, request: SearchRequest) -> bool:
    if request.category is not EvidenceCategory.CORPORATE_EVENT or request.instrument is None:
        return True
    text = f"{result.citation.title} {result.snippet}".lower()
    # Official announcements commonly spell out the company name without repeating
    # its ticker.  Requiring both fields discarded otherwise strong, primary-source
    # evidence.  Either canonical identifier is sufficient, while ticker matching
    # remains digit-bounded so a longer unrelated number cannot pass the check.
    if request.instrument.name.lower() in text:
        return True
    code = re.escape(request.instrument.code.lower())
    return re.search(rf"(?<!\d){code}(?:\.(?:sh|sz|bj))?(?!\d)", text) is not None
