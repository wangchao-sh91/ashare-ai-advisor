"""Quality validation for normalized market records."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain import NormalizedMarketRecord


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: ValidationSeverity
    message: str


class DataValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    usable: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


def validate_market_records(
    records: list[NormalizedMarketRecord],
    *,
    required_fields: set[str],
    numeric_fields: set[str],
    expected_units: dict[str, str],
    min_observations: int,
    unique_dates: bool = True,
    requested_start: date | None = None,
    requested_end: date | None = None,
) -> DataValidationResult:
    """Apply deterministic schema, type, unit, ordering, and coverage checks."""
    issues: list[ValidationIssue] = []
    if not records:
        issues.append(
            ValidationIssue(code="empty", severity=ValidationSeverity.ERROR, message="no records")
        )
    if len(records) < min_observations:
        issues.append(
            ValidationIssue(
                code="insufficient_sample",
                severity=ValidationSeverity.ERROR,
                message=f"requires at least {min_observations} observations",
            )
        )

    dates = [record.observed_at for record in records]
    if dates != sorted(dates):
        issues.append(
            ValidationIssue(
                code="date_order",
                severity=ValidationSeverity.ERROR,
                message="dates are not ascending",
            )
        )
    if unique_dates and len(dates) != len(set(dates)):
        issues.append(
            ValidationIssue(
                code="duplicate_date",
                severity=ValidationSeverity.ERROR,
                message="duplicate dates found",
            )
        )

    for record in records:
        missing = required_fields - set(record.values)
        if missing:
            issues.append(
                ValidationIssue(
                    code="missing_fields",
                    severity=ValidationSeverity.ERROR,
                    message=f"missing canonical fields: {sorted(missing)}",
                )
            )
        for field in numeric_fields & set(record.values):
            value = record.values[field]
            if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
                issues.append(
                    ValidationIssue(
                        code="numeric_type",
                        severity=ValidationSeverity.ERROR,
                        message=f"{field} is not numeric",
                    )
                )
        for field, expected_unit in expected_units.items():
            if field in record.values and record.units.get(field) != expected_unit:
                issues.append(
                    ValidationIssue(
                        code="invalid_unit",
                        severity=ValidationSeverity.ERROR,
                        message=f"{field} must use {expected_unit}",
                    )
                )

    if dates and requested_start is not None and min(dates) > requested_start:
        issues.append(
            ValidationIssue(
                code="partial_start_coverage",
                severity=ValidationSeverity.WARNING,
                message="available data starts after the requested date",
            )
        )
    if dates and requested_end is not None and max(dates) < requested_end:
        issues.append(
            ValidationIssue(
                code="partial_end_coverage",
                severity=ValidationSeverity.WARNING,
                message="available data ends before the requested date",
            )
        )
    return DataValidationResult(
        usable=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        issues=issues,
    )
