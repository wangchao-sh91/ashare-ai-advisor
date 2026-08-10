"""Deterministic web-source quality scoring and conservative deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.domain.models import SourceQuality
from app.providers.search_gateway import SearchResult

PRIMARY_DOMAIN_SUFFIXES = (
    ".gov.cn",
    "gov.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
    "cninfo.com.cn",
    "csindex.com.cn",
    "pbc.gov.cn",
    "stats.gov.cn",
)
PRIMARY_PUBLISHER_TERMS = (
    "证监会",
    "上海证券交易所",
    "深圳证券交易所",
    "北京证券交易所",
    "巨潮资讯",
    "国务院",
    "人民银行",
    "国家统计局",
    "中证指数",
    "公司公告",
)


@dataclass(frozen=True)
class RankedSearchResult:
    result: SearchResult
    source_score: int


def rank_and_deduplicate(results: list[SearchResult]) -> list[RankedSearchResult]:
    """Prefer primary sources and remove only same-URL duplicates.

    Distinct publishers are always retained, even for matching titles, so credible
    conflicts cannot be silently collapsed.
    """
    selected: dict[str, RankedSearchResult] = {}
    for result in results:
        quality = classify_source(result)
        updated = result.model_copy(
            update={"citation": result.citation.model_copy(update={"source_quality": quality})}
        )
        score = (100 if quality is SourceQuality.PRIMARY else 0) + int(result.relevance_score or 0)
        key = canonical_url(str(result.citation.url))
        candidate = RankedSearchResult(updated, score)
        existing = selected.get(key)
        if existing is None or len(updated.snippet) > len(existing.result.snippet):
            selected[key] = candidate
    return sorted(selected.values(), key=lambda item: item.source_score, reverse=True)


def classify_source(result: SearchResult) -> SourceQuality:
    domain = (result.citation.domain or "").lower()
    publisher = result.citation.publisher or ""
    if any(domain == suffix or domain.endswith(f".{suffix}") for suffix in PRIMARY_DOMAIN_SUFFIXES):
        return SourceQuality.PRIMARY
    if any(term in publisher for term in PRIMARY_PUBLISHER_TERMS):
        return SourceQuality.PRIMARY
    return SourceQuality.SECONDARY


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", "")
    )
