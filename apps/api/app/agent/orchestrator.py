"""Bounded, typed orchestration for one stateless research request."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agent.entity_resolution import ContextualEntityResolver, EntityResolution, EntityStatus
from app.agent.execution import ConstrainedToolExecutor, ToolExecutionResult
from app.agent.generation import AnswerGenerationError, AnswerGenerator
from app.agent.planning import EvidencePlan, EvidencePlanner
from app.agent.routing import IntentClassification, IntentClassifier
from app.agent.safety import InvestmentSafetyPolicy, SafetyAction, SafetyDecision
from app.agent.verification import AnswerVerificationError, AnswerVerifier
from app.api.chat_models import ChatRequest
from app.domain import ErrorCode, StructuredAnswer
from app.providers.model_gateway import ModelErrorCode, ModelGatewayError


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
    classification: IntentClassification | None = None
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
        if self.status in {OrchestrationStatus.REFUSED, OrchestrationStatus.FAILED} and not (
            self.error_code
        ):
            raise ValueError("refused or failed result requires an error code")
        return self


class ControlledOrchestrator:
    """Application-owned workflow; no model can discover or select tools."""

    def __init__(
        self,
        *,
        classifier: IntentClassifier,
        entity_resolver: ContextualEntityResolver,
        planner: EvidencePlanner,
        executor: ConstrainedToolExecutor,
        generator: AnswerGenerator,
        verifier: AnswerVerifier | None = None,
        safety_policy: InvestmentSafetyPolicy | None = None,
    ) -> None:
        self._classifier = classifier
        self._entity_resolver = entity_resolver
        self._planner = planner
        self._executor = executor
        self._generator = generator
        self._verifier = verifier or AnswerVerifier()
        self._safety = safety_policy or InvestmentSafetyPolicy()

    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        await _report(progress, OrchestrationStage.ROUTING)
        try:
            classification = await self._classifier.classify(request.question, request.messages)
        except ModelGatewayError as exc:
            return self._model_failure(exc)

        safety = self._safety.evaluate(request.question, classification)
        if safety.action is SafetyAction.REFUSE:
            return OrchestrationResult(
                status=OrchestrationStatus.REFUSED,
                message=safety.message,
                error_code=ErrorCode.UNSUPPORTED_SCOPE,
                classification=classification,
                safety=safety,
            )

        entity = self._entity_resolver.resolve(
            request.question,
            classification,
            request.messages,
        )
        if entity.status is EntityStatus.CLARIFICATION_REQUIRED:
            return OrchestrationResult(
                status=OrchestrationStatus.CLARIFICATION_REQUIRED,
                message=entity.clarification,
                error_code=ErrorCode.AMBIGUOUS_INSTRUMENT,
                classification=classification,
                entity=entity,
                safety=safety,
            )

        effective_question = safety.safe_question or request.question
        plan = self._planner.build(effective_question, classification, entity.instrument)
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
                classification=classification,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )

        try:
            await _report(progress, OrchestrationStage.GENERATION)
            answer = await self._generator.generate(
                effective_question,
                classification,
                execution,
            )
            await _report(progress, OrchestrationStage.VERIFICATION)
            verified = self._verifier.verify(answer, classification, execution)
        except ModelGatewayError as exc:
            return self._model_failure(
                exc,
                classification=classification,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )
        except (AnswerGenerationError, AnswerVerificationError):
            return OrchestrationResult(
                status=OrchestrationStatus.FAILED,
                message="生成结果未通过证据与安全验证。",
                error_code=ErrorCode.VALIDATION_FAILED,
                classification=classification,
                entity=entity,
                safety=safety,
                plan=plan,
                execution=execution,
            )
        return OrchestrationResult(
            status=OrchestrationStatus.ANSWERED,
            answer=verified,
            classification=classification,
            entity=entity,
            safety=safety,
            plan=plan,
            execution=execution,
        )

    @staticmethod
    def _model_failure(
        error: ModelGatewayError,
        *,
        classification: IntentClassification | None = None,
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


async def _report(
    callback: ProgressCallback | None,
    stage: OrchestrationStage,
) -> None:
    if callback is not None:
        await callback(stage)
