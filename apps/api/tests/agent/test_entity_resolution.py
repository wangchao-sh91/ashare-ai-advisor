import pandas as pd

from app.agent.entity_resolution import ContextualEntityResolver, EntitySource, EntityStatus
from app.agent.routing import IntentClassification, IntentKind
from app.api.chat_models import ChatMessage, ChatRole
from app.services.instrument_resolver import InstrumentResolver


def classifier(instrument_query: str | None = None) -> IntentClassification:
    return IntentClassification(
        intent=IntentKind.SINGLE_STOCK,
        instrument_query=instrument_query,
        rationale="research",
    )


def resolver() -> ContextualEntityResolver:
    return ContextualEntityResolver(
        InstrumentResolver(
            pd.DataFrame(
                [
                    {"code": "600519", "name": "贵州茅台"},
                    {"code": "000001", "name": "平安银行"},
                ]
            )
        )
    )


def test_follow_up_uses_current_context() -> None:
    result = resolver().resolve(
        "它的估值呢？",
        classifier(),
        [ChatMessage(role=ChatRole.USER, content="分析贵州茅台近期走势")],
    )

    assert result.status is EntityStatus.RESOLVED
    assert result.instrument is not None and result.instrument.code == "600519"
    assert result.source is EntitySource.CONTEXT


def test_explicit_current_instrument_overrides_prior_context() -> None:
    result = resolver().resolve(
        "改看平安银行的估值",
        classifier("平安银行"),
        [ChatMessage(role=ChatRole.USER, content="分析贵州茅台")],
    )

    assert result.instrument is not None and result.instrument.code == "000001"
    assert result.source is EntitySource.CURRENT_QUESTION


def test_ambiguous_or_missing_instrument_requests_clarification() -> None:
    ambiguous = resolver().resolve("分析000001", classifier("000001"), [])
    missing = resolver().resolve("它怎么样？", classifier(), [])

    assert ambiguous.status is EntityStatus.CLARIFICATION_REQUIRED
    assert len(ambiguous.candidates) == 2
    assert missing.status is EntityStatus.CLARIFICATION_REQUIRED


def test_stable_knowledge_does_not_require_instrument() -> None:
    classification = IntentClassification(
        intent=IntentKind.STABLE_KNOWLEDGE,
        rationale="knowledge",
    )
    result = resolver().resolve("什么是市盈率？", classification, [])
    assert result.status is EntityStatus.NOT_REQUIRED
