"""Structured logging and audit events (SDS-002 §11).

All log records are emitted as structured JSON events carrying the context
fields listed in SDS-002 §11.2. Audit events (immutable records of significant
processing actions) are routed to a dedicated logger so audit trails stay
separate from diagnostic verbosity (SDS-002 §11.5).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from app.utils.ids import utc_now

TRACE = 5
FATAL = logging.CRITICAL + 10

logging.addLevelName(TRACE, "TRACE")
logging.addLevelName(FATAL, "FATAL")

_DIAGNOSTIC_LOGGER = "aet"
_AUDIT_LOGGER = "aet.audit"


@dataclass(frozen=True, slots=True)
class LogEvent:
    """Structured log event model (SDS-002 §11.2)."""

    severity: str
    message: str
    component: str
    operation: str | None = None
    correlation_id: str | None = None
    project_id: str | None = None
    stage: str | None = None
    actor: str = "system"
    error_code: str | None = None
    plugin_id: str | None = None
    plugin_version: str | None = None
    audit: bool = False
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())


class StructuredLogger:
    """Logging API used by all modules (SDS-002 §8.11)."""

    def __init__(self, component: str) -> None:
        self._component = component
        self._diagnostic = logging.getLogger(_DIAGNOSTIC_LOGGER)
        self._audit = logging.getLogger(_AUDIT_LOGGER)

    def _emit(
        self,
        level: int,
        message: str,
        *,
        audit: bool = False,
        **context: str | None,
    ) -> None:
        event = LogEvent(
            severity=logging.getLevelName(level),
            message=message,
            component=self._component,
            audit=audit,
            **context,  # type: ignore[arg-type]
        )
        sink = self._audit if audit else self._diagnostic
        sink.log(level, json.dumps(asdict(event), default=str))

    def trace(self, message: str, **context: str | None) -> None:
        self._emit(TRACE, message, **context)

    def debug(self, message: str, **context: str | None) -> None:
        self._emit(logging.DEBUG, message, **context)

    def info(self, message: str, **context: str | None) -> None:
        self._emit(logging.INFO, message, **context)

    def warn(self, message: str, **context: str | None) -> None:
        self._emit(logging.WARNING, message, **context)

    def error(self, message: str, **context: str | None) -> None:
        self._emit(logging.ERROR, message, **context)

    def fatal(self, message: str, **context: str | None) -> None:
        self._emit(FATAL, message, **context)

    def audit(self, message: str, **context: str | None) -> None:
        """Record an immutable audit event (SDS-002 §11.5)."""
        self._emit(logging.INFO, message, audit=True, **context)


def get_logger(component: str) -> StructuredLogger:
    """Return a structured logger bound to a module/component name."""
    return StructuredLogger(component)
