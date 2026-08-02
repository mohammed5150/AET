"""Processing pipeline orchestration (SDS-002 §7).

Each stage runs behind an explicit boundary with its own status, timing,
error capture, and a shared correlation identifier (SDS-002 §7.3), enabling
diagnostics, partial reruns, and future asynchronous execution.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.core.errors import AETError, ProcessingError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.utils.ids import new_id, utc_now


class PipelineStage(StrEnum):
    """Stages of the DWG-to-report pipeline (SDS-002 §7.1)."""

    INGESTION = "ingestion"
    INTERPRETATION = "interpretation"
    ASSET_DERIVATION = "asset-derivation"
    VALIDATION = "validation"
    REPORTING = "reporting"


class StageStatus(StrEnum):
    """Lifecycle status of one pipeline stage execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


StageStep = Callable[[str], Outcome[object]]


@dataclass(slots=True)
class StageRecord:
    """Immutable-in-spirit record of one stage execution (SDS-002 §7.3)."""

    stage: PipelineStage
    correlation_id: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Aggregate outcome of a pipeline execution."""

    correlation_id: str
    records: list[StageRecord] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return all(record.status is StageStatus.SUCCEEDED for record in self.records)

    def first_failure(self) -> StageRecord | None:
        for record in self.records:
            if record.status is StageStatus.FAILED:
                return record
        return None


class ProcessingPipeline:
    """Runs stage callables sequentially with explicit error boundaries."""

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger or get_logger("pipeline")

    def execute(
        self,
        stages: Sequence[tuple[PipelineStage, StageStep]],
        *,
        correlation_id: str | None = None,
    ) -> PipelineResult:
        """Run each stage in order; later stages are skipped on failure."""
        cid = correlation_id or new_id()
        records: list[StageRecord] = []
        failed = False
        for stage, step in stages:
            record = StageRecord(stage=stage, correlation_id=cid)
            records.append(record)
            if failed:
                record.status = StageStatus.SKIPPED
                continue
            record.status = StageStatus.RUNNING
            record.started_at = utc_now()
            outcome = self._run_step(stage, step, cid)
            record.completed_at = utc_now()
            record.message = outcome.message
            if outcome.success:
                record.status = StageStatus.SUCCEEDED
            else:
                record.status = StageStatus.FAILED
                record.error_code = outcome.error_code
                failed = True
            self._logger.audit(
                f"Stage {stage} {record.status}",
                stage=str(stage),
                operation="pipeline-stage",
                correlation_id=cid,
                error_code=record.error_code,
            )
        return PipelineResult(correlation_id=cid, records=records)

    def _run_step(
        self,
        stage: PipelineStage,
        step: StageStep,
        correlation_id: str,
    ) -> Outcome[object]:
        try:
            return step(correlation_id)
        except AETError as error:
            return Outcome.from_error(error, correlation_id=correlation_id)
        except Exception as exc:  # noqa: BLE001 - stage error boundary
            return Outcome.fail(
                ProcessingError.code,
                f"Unexpected failure in stage '{stage}': {exc}",
                correlation_id=correlation_id,
            )
