"""Validation processing (SDS-002 §8.7).

Concrete rules implement the :class:`ValidationRule` contract (also the
extension point for validation-rule plugins). Rule execution failures are
isolated per rule (SDS-002 §12.2, §10.5): a failing rule is recorded as an
error-severity finding and the run continues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.core.errors import RuleError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.models.asset import Asset, AssetRelation
from app.models.drawing import DrawingSnapshot
from app.models.project import Project
from app.models.validation import (
    RunStatus,
    Severity,
    ValidationResult,
    ValidationRun,
)
from app.utils.ids import utc_now

STAGE_NAME = "validation"


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Everything a rule may inspect when evaluating a project."""

    project: Project
    snapshots: list[DrawingSnapshot] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    relations: list[AssetRelation] = field(default_factory=list)


@runtime_checkable
class ValidationRule(Protocol):
    """Contract for validation rules and rule-pack plugins."""

    rule_id: str
    description: str

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        """Return findings for the given context."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationRunResult:
    """A completed run together with its emitted findings."""

    run: ValidationRun
    results: list[ValidationResult]


class ValidationEngine:
    """Evaluates assets and project structures against rule contracts."""

    stage = STAGE_NAME

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger or get_logger("validation-engine")

    def run(
        self,
        context: ValidationContext,
        rules: list[ValidationRule],
        *,
        correlation_id: str | None = None,
    ) -> Outcome[ValidationRunResult]:
        """Execute all rules, isolating per-rule execution failures."""
        run = ValidationRun(
            project_id=context.project.project_id,
            rule_ids=[rule.rule_id for rule in rules],
        )
        results: list[ValidationResult] = []
        for rule in rules:
            try:
                findings = rule.evaluate(context)
            except Exception as exc:  # noqa: BLE001 - isolate rule failures
                self._logger.error(
                    f"Rule '{rule.rule_id}' execution failed: {exc}",
                    stage=self.stage,
                    project_id=context.project.project_id,
                    correlation_id=correlation_id,
                    error_code=RuleError.code,
                )
                findings = [
                    ValidationResult(
                        rule_id=rule.rule_id,
                        severity=Severity.ERROR,
                        passed=False,
                        message=f"Rule execution failed: {exc}",
                        evidence={"error_class": type(exc).__name__},
                    )
                ]
            for finding in findings:
                finding.run_id = run.run_id
                results.append(finding)
        run.status = RunStatus.COMPLETED
        run.completed_at = utc_now()
        self._logger.audit(
            f"Validation run completed with {len(results)} finding(s)",
            stage=self.stage,
            operation="validation-run",
            project_id=context.project.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(
            ValidationRunResult(run=run, results=results),
            correlation_id=correlation_id,
        )
