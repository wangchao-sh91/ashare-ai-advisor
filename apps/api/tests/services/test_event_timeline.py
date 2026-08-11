from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from pydantic import HttpUrl

from app.domain import (
    Citation,
    EvidenceCategory,
    Exchange,
    Instrument,
    InstrumentType,
    NormalizedMarketRecord,
    SourceType,
)
from app.services.event_timeline import (
    AlignmentRule,
    TimingPrecision,
    align_events,
    calculate_event_windows,
    deduplicate_event_citations,
    event_window_evidence,
)

CN = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 12, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)
TRADING_DATES = [
    date(2026, 8, 7),
    date(2026, 8, 10),
    date(2026, 8, 11),
    date(2026, 8, 12),
    date(2026, 8, 13),
    date(2026, 8, 14),
    date(2026, 8, 17),
]


def citation(identifier: str, published_at: datetime | None, url: str | None = None) -> Citation:
    return Citation(
        id=identifier,
        source_type=SourceType.WEB,
        title="贵州茅台600519.SH公司公告",
        supported_claim="贵州茅台（600519.SH）发布公司公告。",
        category=EvidenceCategory.CORPORATE_EVENT,
        url=HttpUrl(url or f"https://example.com/{identifier}"),
        published_at=published_at,
        retrieved_at=NOW,
    )


def records() -> list[NormalizedMarketRecord]:
    result: list[NormalizedMarketRecord] = []
    for index, observed in enumerate(TRADING_DATES):
        result.append(
            NormalizedMarketRecord(
                id=f"daily:{observed.isoformat()}",
                instrument=STOCK,
                observed_at=observed,
                values={
                    "close": Decimal(100 + index * 2),
                    "volume": Decimal(1000 + index * 100),
                },
                units={"close": "CNY", "volume": "shares"},
                period_start=TRADING_DATES[0],
                period_end=TRADING_DATES[-1],
                cutoff=NOW,
                retrieved_at=NOW,
            )
        )
    return result


def test_deduplication_uses_canonical_url_and_event_identity() -> None:
    first = citation("web:1", datetime(2026, 8, 7, 10, tzinfo=CN), "https://example.com/a?x=1")
    duplicate = citation("web:2", datetime(2026, 8, 7, 10, tzinfo=CN), "https://example.com/a?x=2")
    assert len(deduplicate_event_citations([first, duplicate])) == 1


def test_trading_day_after_close_weekend_date_only_and_undated_alignment() -> None:
    items = [
        citation("same", datetime(2026, 8, 7, 14, tzinfo=CN)),
        citation("after", datetime(2026, 8, 7, 16, tzinfo=CN)),
        citation("weekend", datetime(2026, 8, 8, 10, tzinfo=CN)),
        citation("date-only", datetime(2026, 8, 7, 0, tzinfo=CN)),
        citation("undated", None),
    ]
    events = align_events(items, instrument=STOCK, trading_dates=TRADING_DATES)
    assert [(item.aligned_date, item.alignment_rule) for item in events] == [
        (date(2026, 8, 7), AlignmentRule.SAME_TRADING_DAY),
        (date(2026, 8, 10), AlignmentRule.NEXT_AFTER_CLOSE),
        (date(2026, 8, 10), AlignmentRule.NEXT_NON_TRADING_DAY),
        (date(2026, 8, 10), AlignmentRule.NEXT_DATE_ONLY),
        (None, AlignmentRule.UNDATED),
    ]
    assert events[3].precision is TimingPrecision.DATE_ONLY


def test_one_three_five_day_windows_use_actual_trading_dates_and_sources() -> None:
    event = align_events(
        [citation("event", datetime(2026, 8, 7, 14, tzinfo=CN))],
        instrument=STOCK,
        trading_dates=TRADING_DATES,
    )
    observations = calculate_event_windows(event, records())
    assert [item.horizon for item in observations] == [1, 3, 5]
    assert observations[0].period_end == date(2026, 8, 10)
    assert observations[2].period_end == date(2026, 8, 14)
    assert observations[0].source_ids[0] == "event"
    assert observations[0].formula == "(close_horizon / close_event_day - 1) * 100"


def test_undated_and_boundary_events_do_not_fabricate_windows() -> None:
    items = [
        citation("undated", None),
        citation("boundary", datetime(2026, 8, 17, 14, tzinfo=CN)),
    ]
    events = align_events(items, instrument=STOCK, trading_dates=TRADING_DATES)
    assert calculate_event_windows(events, records()) == []


def test_event_window_evidence_is_temporal_and_marks_date_only_uncertainty() -> None:
    evidence = event_window_evidence(
        [citation("date-only", datetime(2026, 8, 7, 0, tzinfo=CN))],
        records(),
        instrument=STOCK,
    )
    assert [item.period_end for item in evidence] == [
        date(2026, 8, 11),
        date(2026, 8, 13),
        date(2026, 8, 17),
    ]
    assert all("时序观察" in item.claim for item in evidence)
    assert all(item.quality_flags for item in evidence)
