"""Resolve one canonical instrument from the current stateless chat context."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.routing import IntentClassification, IntentKind
from app.api.chat_models import ChatMessage
from app.domain import Instrument
from app.services.instrument_resolver import InstrumentResolver, ResolutionStatus


class EntityStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    NOT_REQUIRED = "not_required"


class EntitySource(StrEnum):
    CURRENT_QUESTION = "current_question"
    CLASSIFIER = "classifier"
    CONTEXT = "context"
    NONE = "none"


class EntityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EntityStatus
    instrument: Instrument | None = None
    candidates: list[Instrument] = Field(default_factory=list, max_length=10)
    source: EntitySource = EntitySource.NONE
    clarification: str | None = Field(default=None, max_length=500)


_RESEARCH_INTENTS = {
    IntentKind.SINGLE_STOCK,
    IntentKind.BROAD_INDEX,
    IntentKind.MIXED,
}


class ContextualEntityResolver:
    def __init__(self, resolver: InstrumentResolver) -> None:
        self._resolver = resolver

    def resolve(
        self,
        question: str,
        classification: IntentClassification,
        context: list[ChatMessage],
    ) -> EntityResolution:
        if classification.intent not in _RESEARCH_INTENTS:
            return EntityResolution(status=EntityStatus.NOT_REQUIRED)

        current = self._resolver.resolve_text(question)
        if current.status is not ResolutionStatus.NOT_FOUND:
            return self._decision(current.status, current.candidates, EntitySource.CURRENT_QUESTION)

        if classification.instrument_query:
            classified = self._resolver.resolve(classification.instrument_query)
            if classified.status is not ResolutionStatus.NOT_FOUND:
                return self._decision(
                    classified.status,
                    classified.candidates,
                    EntitySource.CLASSIFIER,
                )
            return self._clarification([], EntitySource.CLASSIFIER)

        for message in reversed(context):
            prior = self._resolver.resolve_text(message.content)
            if prior.status is not ResolutionStatus.NOT_FOUND:
                return self._decision(prior.status, prior.candidates, EntitySource.CONTEXT)
        return self._clarification([], EntitySource.NONE)

    def _decision(
        self,
        status: ResolutionStatus,
        candidates: list[Instrument],
        source: EntitySource,
    ) -> EntityResolution:
        if status is ResolutionStatus.RESOLVED:
            return EntityResolution(
                status=EntityStatus.RESOLVED,
                instrument=candidates[0],
                candidates=candidates,
                source=source,
            )
        return self._clarification(candidates, source)

    @staticmethod
    def _clarification(candidates: list[Instrument], source: EntitySource) -> EntityResolution:
        choices = "、".join(f"{item.name}（{item.symbol}）" for item in candidates)
        message = (
            f"请明确要研究的一个标的：{choices}。"
            if choices
            else "请提供一个受支持的 A 股名称/代码或宽基指数名称。"
        )
        return EntityResolution(
            status=EntityStatus.CLARIFICATION_REQUIRED,
            candidates=candidates,
            source=source,
            clarification=message,
        )
