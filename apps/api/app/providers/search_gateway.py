"""Provider-independent bounded web-search gateway over Doubao MCP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator

from app.domain.models import Citation, SourceQuality, SourceType
from app.providers.doubao_mcp import McpErrorCode, McpRuntimeError

MAX_SEARCH_TEXT = 2000


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
    result_limit: int = Field(default=10, ge=1, le=50)
    freshness_intent: FreshnessIntent = FreshnessIntent.ANY
    authority_intent: bool = False

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class SearchErrorCode(StrEnum):
    TIMEOUT = "search_timeout"
    UNAVAILABLE = "search_unavailable"
    INVALID_RESPONSE = "search_invalid_response"
    UPSTREAM_ERROR = "search_upstream_error"


class SearchGatewayError(RuntimeError):
    def __init__(self, code: SearchErrorCode) -> None:
        self.code = code
        super().__init__(f"search request failed with {code.value}")


class SearchToolCaller(Protocol):
    async def call_web_search(self, arguments: dict[str, Any]) -> CallToolResult: ...


class ProviderSearchResult(BaseModel):
    """Defensive view of one provider result."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider_id: str = Field(alias="Id")
    title: str = Field(alias="Title", min_length=1, max_length=300)
    snippet: str = Field(alias="Snippet", default="")
    site_name: str | None = Field(alias="SiteName", default=None)
    url: HttpUrl = Field(alias="Url")
    summary: str | None = Field(alias="Summary", default=None)
    publish_time: datetime | None = Field(alias="PublishTime", default=None)
    rank_score: float | None = Field(alias="RankScore", default=None)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: Citation
    snippet: str = Field(max_length=MAX_SEARCH_TEXT)
    relevance_score: float | None = None


class DoubaoSearchGateway:
    def __init__(self, caller: SearchToolCaller) -> None:
        self._caller = caller

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        arguments: dict[str, Any] = {
            "Query": request.query,
            "Count": request.result_limit,
            "SearchType": "web",
            "AuthLevel": 1 if request.authority_intent else 0,
        }
        if time_range := FRESHNESS_TIME_RANGE.get(request.freshness_intent):
            arguments["TimeRange"] = time_range
        try:
            tool_result = await self._caller.call_web_search(arguments)
        except McpRuntimeError as exc:
            code = (
                SearchErrorCode.TIMEOUT
                if exc.code is McpErrorCode.TIMEOUT
                else SearchErrorCode.UNAVAILABLE
            )
            raise SearchGatewayError(code) from exc

        payload = _tool_payload(tool_result)
        if isinstance(payload.get("error"), dict):
            raise SearchGatewayError(SearchErrorCode.UPSTREAM_ERROR)
        raw_results = _find_result_list(payload)
        retrieved_at = datetime.now(UTC)
        normalized: list[SearchResult] = []
        for raw in raw_results:
            try:
                provider_result = ProviderSearchResult.model_validate(raw)
                normalized.append(_normalize(provider_result, retrieved_at))
            except (ValidationError, ValueError):
                continue
        if raw_results and not normalized:
            raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE)
        return normalized


def _tool_payload(result: CallToolResult) -> dict[str, Any]:
    if result.isError:
        raise SearchGatewayError(SearchErrorCode.UPSTREAM_ERROR)
    structured = result.structuredContent
    if isinstance(structured, dict):
        return _unwrap_result_envelope(structured)
    for content in result.content:
        if isinstance(content, TextContent):
            try:
                parsed = json.loads(content.text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return _unwrap_result_envelope(parsed)
    raise SearchGatewayError(SearchErrorCode.INVALID_RESPONSE)


def _unwrap_result_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the lowercase envelope emitted by real MCP CallToolResult payloads."""
    nested = payload.get("result")
    return nested if isinstance(nested, dict) else payload


def _find_result_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "Results", "SearchResult", "WebResults"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for key in ("Result", "Data", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = _find_result_list(nested)
            if found or any(
                name in nested for name in ("results", "Results", "SearchResult", "WebResults")
            ):
                return found
    return []


def _normalize(result: ProviderSearchResult, retrieved_at: datetime) -> SearchResult:
    url = str(result.url)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid citation URL")
    text = (result.summary or result.snippet).strip()[:MAX_SEARCH_TEXT]
    if not text:
        raise ValueError("search result has no bounded evidence text")
    canonical_url = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))
    citation_id = "web:" + sha256(canonical_url.encode()).hexdigest()[:24]
    return SearchResult(
        citation=Citation(
            id=citation_id,
            source_type=SourceType.WEB,
            title=result.title.strip(),
            supported_claim=text,
            snippet=text,
            source_quality=SourceQuality.SECONDARY,
            publisher=result.site_name.strip() if result.site_name else parsed.hostname,
            domain=parsed.hostname.lower(),
            url=HttpUrl(canonical_url),
            published_at=result.publish_time,
            retrieved_at=retrieved_at,
        ),
        snippet=text,
        relevance_score=result.rank_score,
    )
