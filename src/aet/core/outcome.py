"""Structured processing outcomes (SDS-002 §12.3).

Every processing step returns an :class:`Outcome` instead of raising across
module boundaries, so callers always receive success/failure status, a result
payload or machine-readable error code, diagnostics, and trace identifiers
together.
"""

from __future__ import annotations

from dataclasses import dataclass

from aet.core.errors import AETError


@dataclass(frozen=True, slots=True)
class Outcome[T]:
    """Result of a single processing step."""

    success: bool
    payload: T | None = None
    error_code: str | None = None
    message: str = ""
    correlation_id: str | None = None
    remediation: str | None = None

    @classmethod
    def ok(
        cls,
        payload: T,
        *,
        correlation_id: str | None = None,
        message: str = "",
    ) -> Outcome[T]:
        """Build a successful outcome carrying the result payload."""
        return cls(
            success=True,
            payload=payload,
            message=message,
            correlation_id=correlation_id,
        )

    @classmethod
    def fail(
        cls,
        error_code: str,
        message: str,
        *,
        correlation_id: str | None = None,
        remediation: str | None = None,
    ) -> Outcome[T]:
        """Build a failed outcome with a machine-readable error code."""
        return cls(
            success=False,
            error_code=error_code,
            message=message,
            correlation_id=correlation_id,
            remediation=remediation,
        )

    @classmethod
    def from_error(
        cls,
        error: AETError,
        *,
        correlation_id: str | None = None,
    ) -> Outcome[T]:
        """Build a failed outcome from an expected application error."""
        return cls.fail(
            error.code,
            str(error),
            correlation_id=correlation_id,
            remediation=error.remediation,
        )
