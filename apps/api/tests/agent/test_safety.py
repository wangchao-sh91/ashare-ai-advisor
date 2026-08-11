import pytest

from app.agent.routing import IntentKind, QuestionNormalization
from app.agent.safety import InvestmentSafetyPolicy, SafetyAction


def normalized(comparison: bool = False) -> QuestionNormalization:
    return QuestionNormalization(
        rewritten_question="研究问题",
        intent=IntentKind.SINGLE_STOCK,
        clarification_required=True,
        clarification_question="test",
        comparison_requested=comparison,
        rationale="test",
    )


@pytest.mark.parametrize("question", ["贵州茅台能买吗？", "我应该卖出贵州茅台吗？", "适合我吗？"])
def test_trade_and_suitability_requests_are_reframed(question: str) -> None:
    assert InvestmentSafetyPolicy().evaluate(question, normalized()).action is SafetyAction.REFRAME


@pytest.mark.parametrize("question", ["保证明年必涨", "替我下单买入", "分析一只美股"])
def test_guarantees_trading_and_unsupported_assets_are_refused(question: str) -> None:
    assert InvestmentSafetyPolicy().evaluate(question, normalized()).action is SafetyAction.REFUSE


def test_comparison_is_refused_and_objective_research_allowed() -> None:
    assert (
        InvestmentSafetyPolicy().evaluate("比较两只股票", normalized(True)).action
        is SafetyAction.REFUSE
    )
    assert (
        InvestmentSafetyPolicy().evaluate("分析贵州茅台风险", normalized()).action
        is SafetyAction.ALLOW
    )
