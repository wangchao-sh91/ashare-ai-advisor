"""Compatibility view of the canonical entity returned by normalization."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.routing import QuestionNormalization
from app.domain import Instrument


class EntityStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    NOT_REQUIRED = "not_required"


class EntitySource(StrEnum):
    CURRENT_QUESTION = "current_question"
    NORMALIZER = "normalizer"
    CONTEXT = "context"
    NONE = "none"


class EntityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EntityStatus
    instrument: Instrument | None = None
    candidates: list[Instrument] = Field(default_factory=list, max_length=10)
    source: EntitySource = EntitySource.NONE
    clarification: str | None = Field(default=None, max_length=500)


def entity_from_normalization(normalization: QuestionNormalization) -> EntityResolution:
    if normalization.clarification_required:
        return EntityResolution(
            status=EntityStatus.CLARIFICATION_REQUIRED,
            source=EntitySource.NORMALIZER,
            clarification=normalization.clarification_question,
        )
    if normalization.instrument is None:
        return EntityResolution(status=EntityStatus.NOT_REQUIRED)
    return EntityResolution(
        status=EntityStatus.RESOLVED,
        instrument=normalization.instrument,
        candidates=[normalization.instrument],
        source=EntitySource.NORMALIZER,
    )
