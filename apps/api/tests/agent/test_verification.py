from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from app.agent.execution import ToolExecutionResult
from app.agent.routing import IntentClassification, IntentKind
from app.agent.verification import AnswerVerificationError, AnswerVerifier, VerificationIssueCode
from app.domain import (
    AnswerKind,
    Citation,
    EvidenceItem,
    EvidenceKind,
    Limitation,
    LimitationCode,
    SourceType,
    StructuredAnswer,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
FACT = EvidenceItem(
    id="metric:return",
    kind=EvidenceKind.COMPUTED_METRIC,
    claim="区间收益率为10%",
    value=Decimal("10"),
    unit="percent",
    formula="(end/start-1)*100",
    source_ids=["market:1"],
    retrieved_at=NOW,
)
CITATION = Citation(
    id="web:1",
    source_type=SourceType.WEB,
    title="公告",
    supported_claim="区间收益率为10%",
    url=HttpUrl("https://example.com/a"),
    retrieved_at=NOW,
)
LIMITATION = Limitation(
    code=LimitationCode.PARTIAL_DATA,
    message="valuation unavailable",
    affected_categories=["valuation"],
)


def execution() -> ToolExecutionResult:
    return ToolExecutionResult(
        evidence=[FACT],
        citations=[CITATION],
        limitations=[LIMITATION],
        sufficient=True,
    )


def answer(**updates: object) -> StructuredAnswer:
    base = StructuredAnswer(
        kind=AnswerKind.RESEARCH,
        summary="已验证收益率为10%",
        facts=[FACT],
        analysis=["该表现需要结合风险观察"],
        citations=[CITATION],
        answered_at=NOW,
        limitations=[LIMITATION],
    )
    return base.model_copy(update=updates)


def classification(*, current: bool = False) -> IntentClassification:
    return IntentClassification(
        intent=IntentKind.SINGLE_STOCK,
        time_sensitive=current,
        rationale="research",
    )


def test_verified_answer_passes_all_checks() -> None:
    result = AnswerVerifier().verify(answer(), classification(current=True), execution())
    assert result.summary == "已验证收益率为10%"


def test_rejects_ungrounded_numeric_claim_and_missing_current_citation() -> None:
    invalid = answer(summary="预测上涨99%", citations=[])
    with pytest.raises(AnswerVerificationError) as raised:
        AnswerVerifier().verify(invalid, classification(current=True), execution())
    assert VerificationIssueCode.UNGROUNDED_NUMBER in raised.value.issues
    assert VerificationIssueCode.MISSING_CURRENT_CITATION in raised.value.issues


def test_rejects_missing_fact_limitation_and_disclaimer() -> None:
    invalid = answer(facts=[], limitations=[], disclaimer="仅供参考")
    with pytest.raises(AnswerVerificationError) as raised:
        AnswerVerifier().verify(invalid, classification(), execution())
    assert raised.value.issues == {
        VerificationIssueCode.INVALID_SECTION_STRUCTURE,
        VerificationIssueCode.MISSING_LIMITATION,
        VerificationIssueCode.INVALID_DISCLAIMER,
    }
