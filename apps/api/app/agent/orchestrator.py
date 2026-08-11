"""Bounded category-grounded orchestration for one stateless request."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agent.entity_resolution import EntityResolution, EntityStatus, entity_from_normalization
from app.agent.execution import ConstrainedToolExecutor, ToolExecutionResult
from app.agent.generation import AnswerGenerationError, AnswerGenerator
from app.agent.planning import EvidencePlan, EvidencePlanner
from app.agent.routing import QuestionNormalization, QuestionNormalizer
from app.agent.safety import InvestmentSafetyPolicy, SafetyAction, SafetyDecision
from app.api.chat_models import ChatRequest
from app.domain import ErrorCode, StructuredAnswer
from app.providers.model_gateway import ModelErrorCode, ModelGatewayError

logger = logging.getLogger(__name__)


class OrchestrationStatus(StrEnum):
    ANSWERED = "answered"
    CLARIFICATION_REQUIRED = "clarification_required"
    REFUSED = "refused"
    FAILED = "failed"


class OrchestrationStage(StrEnum):
    ROUTING = "routing"
    MARKET_DATA = "market_data"
    WEB_SEARCH = "web_search"
    CALCULATION = "calculation"
    GENERATION = "generation"
    VERIFICATION = "verification"


ProgressCallback = Callable[[OrchestrationStage], Awaitable[None]]


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: OrchestrationStatus
    answer: StructuredAnswer | None = None
    message: str | None = None
    error_code: ErrorCode | None = None
    classification: QuestionNormalization | None = None
    entity: EntityResolution | None = None
    safety: SafetyDecision | None = None
    plan: EvidencePlan | None = None
    execution: ToolExecutionResult | None = None

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> OrchestrationResult:
        if self.status is OrchestrationStatus.ANSWERED and self.answer is None:
            raise ValueError("answered result requires an answer")
        if self.status is not OrchestrationStatus.ANSWERED and not self.message:
            raise ValueError("non-answer result requires a message")
        if (
            self.status in {OrchestrationStatus.REFUSED, OrchestrationStatus.FAILED}
            and not self.error_code
        ):
            raise ValueError("refused or failed result requires an error code")
        return self


class ControlledOrchestrator:
    def __init__(
        self,
        *,
        normalizer: QuestionNormalizer,
        planner: EvidencePlanner,
        executor: ConstrainedToolExecutor,
        generator: AnswerGenerator,
        safety_policy: InvestmentSafetyPolicy | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._planner = planner
        self._executor = executor
        self._generator = generator
        self._safety = safety_policy or InvestmentSafetyPolicy()

    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        await _report(progress, OrchestrationStage.ROUTING)
        try:
            normalization = await self._normalizer.normalize(request.question, request.messages)
        except ModelGatewayError as exc:
            return self._model_failure(exc)
        safety = self._safety.evaluate(request.question, normalization)
        if safety.action is SafetyAction.REFUSE:
            return OrchestrationResult(
                status=OrchestrationStatus.REFUSED,
                message=safety.message,
                error_code=ErrorCode.UNSUPPORTED_SCOPE,
                classification=normalization,
                safety=safety,
            )
        entity = entity_from_normalization(normalization)
        if entity.status is EntityStatus.CLARIFICATION_REQUIRED:
            return OrchestrationResult(
                status=OrchestrationStatus.CLARIFICATION_REQUIRED,
                message=entity.clarification,
                error_code=ErrorCode.AMBIGUOUS_INSTRUMENT,
                classification=normalization,
                entity=entity,
                safety=safety,
            )
        plan = self._planner.build(normalization)
        if plan.market_calls:
            await _report(progress, OrchestrationStage.MARKET_DATA)
        if plan.search_calls:
            await _report(progress, OrchestrationStage.WEB_SEARCH)
        execution = await self._executor.execute(plan)
        if plan.market_calls:
            await _report(progress, OrchestrationStage.CALCULATION)
        if not execution.sufficient:
            return OrchestrationResult(
                status=OrchestrationStatus.FAILED,
                message="没有足够的已验证证据回答该问题。",
                error_code=execution.terminal_error or ErrorCode.MARKET_DATA_UNAVAILABLE,
                classification=normalization,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )
        effective_question = (
            safety.safe_question
            if safety.action is SafetyAction.REFRAME and safety.safe_question
            else normalization.rewritten_question
        )
        try:
            await _report(progress, OrchestrationStage.GENERATION)
            answer = await self._generator.generate(effective_question, normalization, execution)
        except ModelGatewayError as exc:
            return self._model_failure(
                exc,
                classification=normalization,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )
        except AnswerGenerationError:
            logger.warning("answer_generation_evidence_allowlist_failed")
            return OrchestrationResult(
                status=OrchestrationStatus.FAILED,
                message="模型返回了无法解析的证据引用，请重新尝试。",
                error_code=ErrorCode.VALIDATION_FAILED,
                classification=normalization,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )
        return OrchestrationResult(
            status=OrchestrationStatus.ANSWERED,
            answer=answer,
            classification=normalization,
            entity=entity,
            safety=safety,
            plan=plan,
            execution=execution,
        )

    @staticmethod
    def _model_failure(
        error: ModelGatewayError,
        *,
        classification: QuestionNormalization | None = None,
        entity: EntityResolution | None = None,
        safety: SafetyDecision | None = None,
        plan: EvidencePlan | None = None,
        execution: ToolExecutionResult | None = None,
    ) -> OrchestrationResult:
        code = (
            ErrorCode.PROVIDER_RATE_LIMITED
            if error.code is ModelErrorCode.RATE_LIMITED
            else ErrorCode.MODEL_UNAVAILABLE
        )
        return OrchestrationResult(
            status=OrchestrationStatus.FAILED,
            message="模型服务当前不可用，请稍后重试。",
            error_code=code,
            classification=classification,
            entity=entity,
            safety=safety,
            plan=plan,
            execution=execution,
        )


async def _report(callback: ProgressCallback | None, stage: OrchestrationStage) -> None:
    if callback is not None:
        await callback(stage)
