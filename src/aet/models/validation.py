"""Validation domain models (SDS-002 §8.7, §9.2.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aet.utils.ids import new_id, utc_now


class Severity(StrEnum):
    """Severity scale for validation findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RunStatus(StrEnum):
    """Lifecycle status of a validation run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class ValidationResult:
    """A single severity-based finding with traceable evidence references."""

    rule_id: str
    severity: Severity
    passed: bool
    message: str
    asset_id: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)
    run_id: str = ""
    result_id: str = field(default_factory=new_id)
    executed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ValidationRun:
    """One execution of a set of validation rules against a project."""

    project_id: str
    rule_ids: list[str] = field(default_factory=list)
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    run_id: str = field(default_factory=new_id)
