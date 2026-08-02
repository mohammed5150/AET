"""Error taxonomy for expected application failures (SDS-002 §12.2).

Expected domain errors derive from :class:`AETError` and carry a stable
machine-readable code, a category matching the SDS-002 error taxonomy, and an
optional remediation hint. Unexpected system failures should remain ordinary
exceptions so the two are distinguishable at error boundaries (SDS-002 §12.1).
"""

from __future__ import annotations


class AETError(Exception):
    """Base class for all expected application errors."""

    code: str = "AET_ERROR"
    category: str = "system"

    def __init__(self, message: str, *, remediation: str | None = None) -> None:
        super().__init__(message)
        self.remediation = remediation


class InputError(AETError):
    """Missing files, unsupported formats, or corrupt drawing sources."""

    code = "INPUT_ERROR"
    category = "input"


class ProcessingError(AETError):
    """Parsing, transformation, or derivation failures."""

    code = "PROCESSING_ERROR"
    category = "processing"


class RuleError(AETError):
    """Invalid rule configuration, rule execution failure, or bad context."""

    code = "VALIDATION_ERROR"
    category = "validation"


class InfrastructureError(AETError):
    """Database, storage, plugin loading, or configuration failures."""

    code = "INFRASTRUCTURE_ERROR"
    category = "infrastructure"


class WorkflowError(AETError):
    """Invalid operation sequencing, missing prerequisites, state conflicts."""

    code = "WORKFLOW_ERROR"
    category = "workflow"
