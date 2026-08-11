from app.agent.entity_resolution import EntityStatus, entity_from_normalization
from app.agent.routing import IntentKind, QuestionNormalization
from app.domain import Exchange, Instrument, InstrumentType


def test_entity_is_derived_without_runtime_catalog() -> None:
    instrument = Instrument(
        name="贵州茅台",
        code="600519",
        exchange=Exchange.SSE,
        instrument_type=InstrumentType.STOCK,
    )
    normalized = QuestionNormalization(
        rewritten_question="分析贵州茅台",
        intent=IntentKind.SINGLE_STOCK,
        instrument=instrument,
        rationale="resolved",
    )
    entity = entity_from_normalization(normalized)
    assert entity.status is EntityStatus.RESOLVED
    assert entity.instrument == instrument
