"""Drawing interpretation and normalization (SDS-002 §8.5, SDS-003).

Format-specific interpretation rules live behind the
:class:`DrawingInterpreter` contract (also the extension point for
drawing-interpreter plugins) so they stay isolated from asset logic.
Interpreters are selected per source format from an
:class:`~app.modules.drawing_engine.registry.InterpreterRegistry` unless one
is injected explicitly (SDS-003 §4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.core.errors import AETError, InputError, ProcessingError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.models.drawing import DrawingSnapshot
from app.models.project import SourceInput
from app.modules.drawing_engine.registry import (
    InterpreterRegistry,
    default_registry,
)

STAGE_NAME = "interpretation"


class DrawingInterpreter(Protocol):
    """Contract for format- or source-specific normalization strategies."""

    def interpret(self, source: SourceInput) -> DrawingSnapshot:
        """Convert one source input into a normalized drawing snapshot."""
        ...


class PassthroughInterpreter:
    """Format-agnostic strategy producing an empty provenance snapshot.

    Retained for tests and callers that need interpretation without a real
    format backend; not registered for any format (SDS-003 supersedes it as
    the default).
    """

    def interpret(self, source: SourceInput) -> DrawingSnapshot:
        return DrawingSnapshot(
            project_id=source.project_id,
            source_input_id=source.input_id,
            metadata={
                "source_path": source.path,
                "source_hash": source.file_hash,
            },
        )


class DrawingEngine:
    """Normalizes source drawings into internal models."""

    stage = STAGE_NAME

    def __init__(
        self,
        interpreter: DrawingInterpreter | None = None,
        registry: InterpreterRegistry | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._interpreter = interpreter
        self._registry = registry if registry is not None else default_registry()
        self._logger = logger or get_logger("drawing-engine")

    @property
    def registry(self) -> InterpreterRegistry:
        """Registry used for format-based interpreter selection."""
        return self._registry

    def normalize(
        self,
        source: SourceInput,
        *,
        correlation_id: str | None = None,
    ) -> Outcome[DrawingSnapshot]:
        """Produce a normalized snapshot for one registered source input."""
        interpreter = self._interpreter or self._select(source)
        if interpreter is None:
            error = self._unsupported_format(source)
            self._log_failure(error.code, str(error), source, correlation_id)
            return Outcome.from_error(error, correlation_id=correlation_id)
        try:
            snapshot = interpreter.interpret(source)
        except AETError as error:
            self._log_failure(error.code, str(error), source, correlation_id)
            return Outcome.from_error(error, correlation_id=correlation_id)
        except Exception as exc:  # noqa: BLE001 - wrap interpreter failures
            message = f"Drawing interpretation failed for {source.path}: {exc}"
            self._log_failure(ProcessingError.code, message, source, correlation_id)
            return Outcome.fail(
                ProcessingError.code, message, correlation_id=correlation_id
            )
        self._logger.info(
            "Drawing normalized",
            stage=self.stage,
            project_id=source.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(snapshot, correlation_id=correlation_id)

    def _select(self, source: SourceInput) -> DrawingInterpreter | None:
        return self._registry.lookup(self._format_of(source))

    def _unsupported_format(self, source: SourceInput) -> InputError:
        format_id = self._format_of(source) or "unknown"
        if format_id == "dwg":
            remediation = "Convert the DWG file to DXF and re-import it."
        else:
            supported = ", ".join(self._registry.formats()) or "none"
            remediation = f"Supported formats: {supported}."
        return InputError(
            f"No interpreter registered for format '{format_id}' " f"({source.path})",
            remediation=remediation,
        )

    def _format_of(self, source: SourceInput) -> str:
        return source.file_format or Path(source.path).suffix.lower().lstrip(".")

    def _log_failure(
        self,
        error_code: str,
        message: str,
        source: SourceInput,
        correlation_id: str | None,
    ) -> None:
        self._logger.error(
            message,
            stage=self.stage,
            project_id=source.project_id,
            correlation_id=correlation_id,
            error_code=error_code,
        )
