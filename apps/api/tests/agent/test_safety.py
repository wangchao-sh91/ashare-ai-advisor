import pytest

from app.agent.routing import IntentClassification, IntentKind
from app.agent.safety import InvestmentSafetyPolicy, SafetyAction, SafetyViolation


def classification(**updates: object) -> IntentClassification:
    return IntentClassification(
        intent=IntentKind.SINGLE_STOCK,
        instrument_query="贵州茅台",
        rationale="research",
    ).model_copy(update=updates)


@pytest.mark.parametrize("question", ["贵州茅台能买吗？", "我应该卖出贵州茅台吗？", "适合我吗？"])
def test_trade_and_suitability_requests_are_reframed(question: str) -> None:
    result = InvestmentSafetyPolicy().evaluate(question, classification())
    assert result.action is SafetyAction.REFRAME
    assert result.safe_question is not None and "风险" in result.safe_question


@pytest.mark.parametrize("question", ["保证贵州茅台明年必涨", "替我下单买入", "分析一只美股"])
def test_guarantees_trading_and_unsupported_assets_are_refused(question: str) -> None:
    result = InvestmentSafetyPolicy().evaluate(question, classification())
    assert result.action is SafetyAction.REFUSE
    assert result.message is not None


def test_multi_instrument_comparison_is_refused() -> None:
    result = InvestmentSafetyPolicy().evaluate(
        "比较贵州茅台和五粮液",
        classification(comparison_requested=True),
    )
    assert result.action is SafetyAction.REFUSE
    assert SafetyViolation.MULTI_INSTRUMENT_COMPARISON in result.violations


def test_objective_single_instrument_research_is_allowed() -> None:
    result = InvestmentSafetyPolicy().evaluate("分析贵州茅台的估值", classification())
    assert result.action is SafetyAction.ALLOW
    assert result.safe_question == "分析贵州茅台的估值"
