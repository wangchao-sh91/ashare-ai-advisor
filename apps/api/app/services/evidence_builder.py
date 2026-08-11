"""Convert validated market facts and deterministic metrics into evidence."""

from datetime import date
from decimal import Decimal

from app.domain import EvidenceItem, EvidenceKind, Instrument, NormalizedMarketRecord
from app.services.analytics import MetricResult


def _evidence_value(value: object) -> Decimal | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (Decimal, int)):
        return Decimal(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def market_fact_to_evidence(
    record: NormalizedMarketRecord,
    *,
    field_name: str,
    claim: str,
) -> EvidenceItem:
    """Create traceable evidence for one validated normalized field."""
    if field_name not in record.values:
        raise ValueError(f"canonical field {field_name} is unavailable")
    return EvidenceItem(
        id=f"evidence:{record.id}:{field_name}",
        kind=EvidenceKind.MARKET_FACT,
        category=record.category,
        claim=claim,
        value=_evidence_value(record.values[field_name]),
        unit=record.units.get(field_name),
        instrument=record.instrument,
        period_start=record.period_start or record.observed_at,
        period_end=record.period_end or record.observed_at,
        source_ids=[record.id],
        cutoff=record.cutoff,
        retrieved_at=record.retrieved_at,
    )


def metric_to_evidence(
    metric: MetricResult,
    *,
    instrument: Instrument,
    claim: str,
    source_records: list[NormalizedMarketRecord],
) -> EvidenceItem:
    """Create computed evidence while deriving freshness from every input record."""
    records_by_id = {record.id: record for record in source_records}
    missing = set(metric.source_ids) - records_by_id.keys()
    if missing:
        raise ValueError(f"metric input records are unavailable: {sorted(missing)}")
    inputs = [records_by_id[source_id] for source_id in metric.source_ids]
    return EvidenceItem(
        id=f"metric:{metric.metric}:{instrument.symbol}:{metric.period_end.isoformat()}",
        kind=EvidenceKind.COMPUTED_METRIC,
        category=source_records[0].category if source_records else None,
        claim=claim,
        value=metric.value,
        unit=metric.unit,
        instrument=instrument,
        period_start=metric.period_start,
        period_end=metric.period_end,
        formula=metric.formula,
        source_ids=list(metric.source_ids),
        cutoff=min(record.cutoff for record in inputs),
        retrieved_at=max(record.retrieved_at for record in inputs),
        quality_flags=list(metric.quality_flags),
    )
