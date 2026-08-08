"""Structured logging and audit events (SDS-002 §11).

All log records are emitted as structured JSON events carrying the context
fields listed in SDS-002 §11.2. Audit events (immutable records of significant
processing actions) are routed to a dedicated logger so audit trails stay
separate from diagnostic verbosity (SDS-002 §11.5).

Emitting an event is not the same as storing one: until
:func:`configure_logging` attaches sinks, the standard library discards every
record below WARNING. The CLI configures sinks once at startup; library
callers that want persisted logs must do the same.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from app.core.errors import InfrastructureError
from app.utils.ids import utc_now

if TYPE_CHECKING:
    from app.core.config import AppConfig

TRACE = 5
FATAL = logging.CRITICAL + 10

logging.addLevelName(TRACE, "TRACE")
logging.addLevelName(FATAL, "FATAL")

DIAGNOSTIC_LOGGER_NAME = "aet"
AUDIT_LOGGER_NAME = "aet.audit"

DIAGNOSTIC_LOG_FILE = "aet.log"
AUDIT_LOG_FILE = "audit.log"

LEVEL_NAMES: tuple[str, ...] = (
    "TRACE",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
    "FATAL",
)

# Marks the handlers this module owns, so resetting sinks never removes a
# handler installed by an embedding application or by pytest's caplog.
_MANAGED_FLAG = "_aet_managed_sink"


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
        self._diagnostic = logging.getLogger(DIAGNOSTIC_LOGGER_NAME)
        self._audit = logging.getLogger(AUDIT_LOGGER_NAME)

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


def resolve_level(name: str) -> int:
    """Translate a level name into its numeric value.

    Raises :class:`InfrastructureError` for an unknown name, so a bad
    ``log_level`` setting fails at configuration time (SDS-002 §12.2).
    """
    level = logging.getLevelName(str(name).strip().upper())
    if not isinstance(level, int):
        raise InfrastructureError(
            f"Unknown log level: {name}",
            remediation=f"Supported levels are: {', '.join(LEVEL_NAMES)}.",
        )
    return level


def configure_logging(config: AppConfig) -> None:
    """Attach the console, file, and audit sinks of SDS-002 §11.4.

    Diagnostic records go to stderr and ``<log_dir>/aet.log``; audit records
    go only to ``<log_dir>/audit.log``, with propagation disabled so audit
    trails never inherit diagnostic verbosity (SDS-002 §11.5). Repeated calls
    replace the sinks installed by earlier calls, leaving handlers owned by
    anyone else in place.
    """
    level = resolve_level(config.log_level)
    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        diagnostic_file: logging.Handler = logging.FileHandler(
            config.log_dir / DIAGNOSTIC_LOG_FILE, encoding="utf-8"
        )
        audit_file: logging.Handler = logging.FileHandler(
            config.log_dir / AUDIT_LOG_FILE, encoding="utf-8"
        )
    except OSError as exc:
        raise InfrastructureError(
            f"Cannot open the log directory {config.log_dir}: {exc}",
            remediation=(
                "Point log_dir (AET_LOG_DIR or --log-dir) at a writable directory."
            ),
        ) from exc

    diagnostic = logging.getLogger(DIAGNOSTIC_LOGGER_NAME)
    _reset_managed_sinks(diagnostic)
    diagnostic.setLevel(level)
    diagnostic.addHandler(_managed(logging.StreamHandler()))
    diagnostic.addHandler(_managed(diagnostic_file))

    audit = logging.getLogger(AUDIT_LOGGER_NAME)
    _reset_managed_sinks(audit)
    audit.setLevel(logging.INFO)
    audit.propagate = False
    audit.addHandler(_managed(audit_file))


def reset_logging() -> None:
    """Remove the sinks installed by :func:`configure_logging`.

    Restores the untouched-import state so tests and embedding applications
    are not left with process-wide handlers or a silenced audit logger.
    """
    for name in (DIAGNOSTIC_LOGGER_NAME, AUDIT_LOGGER_NAME):
        logger = logging.getLogger(name)
        _reset_managed_sinks(logger)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def _managed(handler: logging.Handler) -> logging.Handler:
    """Tag a handler as owned by this module and emit the raw JSON event."""
    handler.setFormatter(logging.Formatter("%(message)s"))
    setattr(handler, _MANAGED_FLAG, True)
    return handler


def _reset_managed_sinks(logger: logging.Logger) -> None:
    for handler in [
        handler for handler in logger.handlers if getattr(handler, _MANAGED_FLAG, False)
    ]:
        logger.removeHandler(handler)
        handler.close()
