"""Deterministic final-answer evidence, citation, section, and safety checks."""

import re
from enum import StrEnum

from app.agent.execution import ToolExecutionResult
from app.agent.routing import IntentClassification, IntentKind
from app.domain import INVESTMENT_DISCLAIMER, AnswerKind, SourceType, StructuredAnswer

_NUMBER = re.compile(r"(?<![A-Za-z0-9_:])[-+]?\d+(?:\.\d+)?%?")


class VerificationIssueCode(StrEnum):
    UNKNOWN_EVIDENCE = "unknown_evidence"
    UNGROUNDED_NUMBER = "ungrounded_number"
    MISSING_CURRENT_CITATION = "missing_current_citation"
    INVALID_SECTION_STRUCTURE = "invalid_section_structure"
    MISSING_LIMITATION = "missing_limitation"
    INVALID_DISCLAIMER = "invalid_disclaimer"


class AnswerVerificationError(ValueError):
    def __init__(self, issues: set[VerificationIssueCode]) -> None:
        self.issues = frozenset(issues)
        rendered = ",".join(sorted(issue.value for issue in issues))
        super().__init__(f"answer verification failed: {rendered}")


class AnswerVerifier:
    def verify(
        self,
        answer: StructuredAnswer,
        classification: IntentClassification,
        execution: ToolExecutionResult,
    ) -> StructuredAnswer:
        issues: set[VerificationIssueCode] = set()
        allowed_facts = {item.id: item for item in execution.evidence}
        allowed_citations = {item.id: item for item in execution.citations}
        if any(
            item.id not in allowed_facts or item != allowed_facts[item.id] for item in answer.facts
        ) or any(
            item.id not in allowed_citations or item != allowed_citations[item.id]
            for item in answer.citations
        ):
            issues.add(VerificationIssueCode.UNKNOWN_EVIDENCE)

        if classification.intent in {
            IntentKind.SINGLE_STOCK,
            IntentKind.BROAD_INDEX,
            IntentKind.MIXED,
        }:
            if answer.kind not in {AnswerKind.RESEARCH, AnswerKind.MIXED} or (
                execution.evidence and not answer.facts
            ):
                issues.add(VerificationIssueCode.INVALID_SECTION_STRUCTURE)
            narrative = "\n".join([answer.summary, *answer.analysis, *answer.risks])
            evidence_text = "\n".join(
                item.model_dump_json() for item in [*answer.facts, *answer.citations]
            )
            if set(_NUMBER.findall(narrative)) - set(_NUMBER.findall(evidence_text)):
                issues.add(VerificationIssueCode.UNGROUNDED_NUMBER)
        elif classification.intent is IntentKind.STABLE_KNOWLEDGE:
            if answer.kind is not AnswerKind.KNOWLEDGE:
                issues.add(VerificationIssueCode.INVALID_SECTION_STRUCTURE)

        if (
            classification.time_sensitive
            and execution.current_claim_verified
            and not any(item.source_type is SourceType.WEB for item in answer.citations)
        ):
            issues.add(VerificationIssueCode.MISSING_CURRENT_CITATION)

        required_limitations = {
            (item.code, item.message, tuple(item.affected_categories))
            for item in execution.limitations
        }
        actual_limitations = {
            (item.code, item.message, tuple(item.affected_categories))
            for item in answer.limitations
        }
        if not required_limitations <= actual_limitations:
            issues.add(VerificationIssueCode.MISSING_LIMITATION)
        if answer.disclaimer != INVESTMENT_DISCLAIMER:
            issues.add(VerificationIssueCode.INVALID_DISCLAIMER)
        if issues:
            raise AnswerVerificationError(issues)
        return answer
