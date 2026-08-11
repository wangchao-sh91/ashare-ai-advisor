"""Deterministic investment-safety and supported-scope policy."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.routing import IntentKind, QuestionNormalization


class SafetyAction(StrEnum):
    ALLOW = "allow"
    REFRAME = "reframe"
    REFUSE = "refuse"


class SafetyViolation(StrEnum):
    DIRECT_TRADE_INSTRUCTION = "direct_trade_instruction"
    GUARANTEED_PREDICTION = "guaranteed_prediction"
    PERSONALIZED_SUITABILITY = "personalized_suitability"
    AUTOMATED_TRADING = "automated_trading"
    UNSUPPORTED_ASSET = "unsupported_asset"
    MULTI_INSTRUMENT_COMPARISON = "multi_instrument_comparison"


class SafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: SafetyAction
    violations: list[SafetyViolation] = Field(default_factory=list)
    safe_question: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=1000)


_DIRECT_TRADE = re.compile(r"该不该(买|卖|持有)|能不能买|能买吗|买入|卖出|抄底|清仓|持有吗", re.I)
_GUARANTEE = re.compile(r"保证|稳赚|必涨|必跌|确定.{0,8}(收益|价格)|精确.{0,8}(预测|目标价)", re.I)
_PERSONAL = re.compile(r"适合我|我应该|按我的|我的风险承受|为我推荐", re.I)
_AUTOMATED = re.compile(r"替我下单|自动交易|自动买卖|执行交易", re.I)
_UNSUPPORTED = re.compile(
    r"港股|美股|基金|债券|期货|期权|外汇|加密货币|投资组合|行业|概念板块|上传|文件分析",
    re.I,
)


class InvestmentSafetyPolicy:
    def evaluate(
        self,
        question: str,
        classification: QuestionNormalization,
    ) -> SafetyDecision:
        violations: list[SafetyViolation] = []
        if classification.comparison_requested:
            violations.append(SafetyViolation.MULTI_INSTRUMENT_COMPARISON)
        if _UNSUPPORTED.search(question):
            violations.append(SafetyViolation.UNSUPPORTED_ASSET)
        if _AUTOMATED.search(question):
            violations.append(SafetyViolation.AUTOMATED_TRADING)
        if _GUARANTEE.search(question):
            violations.append(SafetyViolation.GUARANTEED_PREDICTION)
        if classification.intent is IntentKind.OUT_OF_SCOPE and not violations:
            violations.append(SafetyViolation.UNSUPPORTED_ASSET)

        if violations:
            return SafetyDecision(
                action=SafetyAction.REFUSE,
                violations=list(dict.fromkeys(violations)),
                message=(
                    "该请求超出首版单一 A 股或受支持宽基指数的研究范围，或要求无法保证的"
                    "预测/交易操作。可以改问一个受支持标的的客观数据、影响因素与风险。"
                ),
            )

        reframe: list[SafetyViolation] = []
        if _DIRECT_TRADE.search(question):
            reframe.append(SafetyViolation.DIRECT_TRADE_INSTRUCTION)
        if _PERSONAL.search(question):
            reframe.append(SafetyViolation.PERSONALIZED_SUITABILITY)
        if reframe:
            instrument = classification.instrument_query or "该标的"
            return SafetyDecision(
                action=SafetyAction.REFRAME,
                violations=reframe,
                safe_question=f"请基于可验证证据分析{instrument}的现状、主要风险与研究关注点。",
                message="不提供直接买卖或个性化适配结论，已改为客观研究分析。",
            )
        return SafetyDecision(action=SafetyAction.ALLOW, safe_question=question)
