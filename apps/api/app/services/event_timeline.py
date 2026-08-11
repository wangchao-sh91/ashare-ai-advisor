"""Conservative corporate-event deduplication, trading-day alignment, and windows."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from app.domain import (
    Citation,
    EvidenceCategory,
    EvidenceItem,
    EvidenceKind,
    Instrument,
    NormalizedMarketRecord,
    QualityFlag,
    QualityFlagCode,
)


class TimingPrecision(StrEnum):
    EXACT = "exact"
    DATE_ONLY = "date_only"
    UNKNOWN = "unknown"


class AlignmentRule(StrEnum):
    SAME_TRADING_DAY = "same_trading_day"
    NEXT_AFTER_CLOSE = "next_after_close"
    NEXT_NON_TRADING_DAY = "next_non_trading_day"
    NEXT_DATE_ONLY = "next_date_only"
    UNDATED = "undated"
    OUTSIDE_CALENDAR = "outside_calendar"


class CorporateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    instrument: Instrument
    title: str
    claim: str
    citation_id: str
    published_at: datetime | None = None
    precision: TimingPrecision
    aligned_date: date | None = None
    alignment_rule: AlignmentRule


class EventWindowObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    horizon: int = Field(ge=1, le=5)
    period_start: date
    period_end: date
    price_return_pct: Decimal
    volume_change_pct: Decimal | None = None
    source_ids: list[str]
    formula: str


def deduplicate_event_citations(citations: list[Citation]) -> list[Citation]:
    selected: dict[tuple[str, str, str], Citation] = {}
    for citation in citations:
        if citation.category is not EvidenceCategory.CORPORATE_EVENT or citation.url is None:
            continue
        parsed = urlsplit(str(citation.url))
        canonical = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", "")
        )
        event_date = (
            citation.published_at.date().isoformat() if citation.published_at else "undated"
        )
        identity = (canonical, citation.title.strip().lower(), event_date)
        current = selected.get(identity)
        if current is None or len(citation.supported_claim) > len(current.supported_claim):
            selected[identity] = citation
    return list(selected.values())


def align_events(
    citations: list[Citation],
    *,
    instrument: Instrument,
    trading_dates: list[date],
    market_close: time = time(15, 0),
) -> list[CorporateEvent]:
    calendar = sorted(set(trading_dates))
    events: list[CorporateEvent] = []
    for citation in deduplicate_event_citations(citations):
        published = citation.published_at
        precision = (
            TimingPrecision.UNKNOWN
            if published is None
            else TimingPrecision.DATE_ONLY
            if published.timetz().replace(tzinfo=None) == time.min
            else TimingPrecision.EXACT
        )
        aligned, rule = _aligned_date(published, precision, calendar, market_close)
        identity = f"{citation.id}:{published.isoformat() if published else 'undated'}"
        events.append(
            CorporateEvent(
                id="event:" + sha256(identity.encode()).hexdigest()[:24],
                instrument=instrument,
                title=citation.title,
                claim=citation.supported_claim,
                citation_id=citation.id,
                published_at=published,
                precision=precision,
                aligned_date=aligned,
                alignment_rule=rule,
            )
        )
    return events


def calculate_event_windows(
    events: list[CorporateEvent],
    records: list[NormalizedMarketRecord],
    *,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> list[EventWindowObservation]:
    ordered = sorted(records, key=lambda item: item.observed_at)
    positions = {record.observed_at: index for index, record in enumerate(ordered)}
    observations: list[EventWindowObservation] = []
    for event in events:
        if event.aligned_date is None or event.aligned_date not in positions:
            continue
        start_index = positions[event.aligned_date]
        start = ordered[start_index]
        start_close = _number(start, "close")
        start_volume = _number(start, "volume")
        if start_close <= 0:
            continue
        for horizon in horizons:
            target_index = start_index + horizon
            if target_index >= len(ordered):
                continue
            target = ordered[target_index]
            target_close = _number(target, "close")
            target_volume = _number(target, "volume")
            observations.append(
                EventWindowObservation(
                    event_id=event.id,
                    horizon=horizon,
                    period_start=start.observed_at,
                    period_end=target.observed_at,
                    price_return_pct=(target_close / start_close - Decimal(1)) * Decimal(100),
                    volume_change_pct=(
                        None
                        if start_volume == 0
                        else (target_volume / start_volume - Decimal(1)) * Decimal(100)
                    ),
                    source_ids=[event.citation_id, start.id, target.id],
                    formula="(close_horizon / close_event_day - 1) * 100",
                )
            )
    return observations


def event_window_evidence(
    citations: list[Citation],
    records: list[NormalizedMarketRecord],
    *,
    instrument: Instrument,
) -> list[EvidenceItem]:
    events = align_events(
        citations,
        instrument=instrument,
        trading_dates=[item.observed_at for item in records],
    )
    events_by_id = {item.id: item for item in events}
    now = max((item.retrieved_at for item in records), default=datetime.now(UTC))
    evidence: list[EvidenceItem] = []
    for observation in calculate_event_windows(events, records):
        event = events_by_id[observation.event_id]
        flags = (
            [
                QualityFlag(
                    code=QualityFlagCode.TIMING_UNCERTAIN, detail="公告仅有日期，按下一交易日对齐"
                )
            ]
            if event.precision is TimingPrecision.DATE_ONLY
            else []
        )
        evidence.append(
            EvidenceItem(
                id=f"metric:event_window:{event.id}:{observation.horizon}",
                kind=EvidenceKind.COMPUTED_METRIC,
                category=EvidenceCategory.CORPORATE_EVENT,
                claim=f"公告对齐日后{observation.horizon}个交易日价格时序观察",
                value=observation.price_return_pct,
                unit="percent",
                instrument=instrument,
                period_start=observation.period_start,
                period_end=observation.period_end,
                formula=observation.formula,
                source_ids=observation.source_ids,
                cutoff=datetime.combine(observation.period_end, time.min, tzinfo=UTC),
                retrieved_at=now,
                quality_flags=flags,
            )
        )
    return evidence


def _aligned_date(
    published: datetime | None,
    precision: TimingPrecision,
    calendar: list[date],
    market_close: time,
) -> tuple[date | None, AlignmentRule]:
    if published is None:
        return None, AlignmentRule.UNDATED
    published_date = published.date()
    if precision is TimingPrecision.DATE_ONLY:
        next_day = next((item for item in calendar if item > published_date), None)
        return (
            next_day,
            AlignmentRule.NEXT_DATE_ONLY if next_day else AlignmentRule.OUTSIDE_CALENDAR,
        )
    if published_date in calendar and published.timetz().replace(tzinfo=None) <= market_close:
        return published_date, AlignmentRule.SAME_TRADING_DAY
    next_day = next((item for item in calendar if item > published_date), None)
    if next_day is None:
        return None, AlignmentRule.OUTSIDE_CALENDAR
    rule = (
        AlignmentRule.NEXT_AFTER_CLOSE
        if published_date in calendar
        else AlignmentRule.NEXT_NON_TRADING_DAY
    )
    return next_day, rule


def _number(record: NormalizedMarketRecord, field: str) -> Decimal:
    value = record.values.get(field)
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ValueError(f"{field} must be numeric")
    return Decimal(value)
