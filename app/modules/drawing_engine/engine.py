"""Drawing interpretation and normalization (SDS-002 §8.5).

Format-specific interpretation rules live behind the
:class:`DrawingInterpreter` contract (also the extension point for
drawing-interpreter plugins) so they stay isolated from asset logic.
"""

from __future__ import annotations

from typing import Protocol

from app.core.errors import AETError, ProcessingError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.models.drawing import DrawingSnapshot
from app.models.project import SourceInput

STAGE_NAME = "interpretation"


class DrawingInterpreter(Protocol):
    """Contract for format- or source-specific normalization strategies."""

    def interpret(self, source: SourceInput) -> DrawingSnapshot:
        """Convert one source input into a normalized drawing snapshot."""
        ...


class PassthroughInterpreter:
    """Placeholder normalization strategy.

    SDS-002 keeps concrete interpretation algorithms out of scope, so the
    default interpreter produces an empty normalized snapshot that carries
    source provenance for traceability.
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
        logger: StructuredLogger | None = None,
    ) -> None:
        self._interpreter = interpreter or PassthroughInterpreter()
        self._logger = logger or get_logger("drawing-engine")

    def normalize(
        self,
        source: SourceInput,
        *,
        correlation_id: str | None = None,
    ) -> Outcome[DrawingSnapshot]:
        """Produce a normalized snapshot for one registered source input."""
        try:
            snapshot = self._interpreter.interpret(source)
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
