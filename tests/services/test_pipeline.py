"""Tests for pipeline stage boundaries (SDS-002 §7.3, §12.4)."""

from app.core.errors import InputError
from app.core.outcome import Outcome
from app.services.pipeline import (
    PipelineStage,
    ProcessingPipeline,
    StageStatus,
)


def test_successful_stages_share_one_correlation_id():
    pipeline = ProcessingPipeline()
    result = pipeline.execute(
        [
            (
                PipelineStage.INTERPRETATION,
                lambda cid: Outcome.ok("a", correlation_id=cid),
            ),
            (
                PipelineStage.ASSET_DERIVATION,
                lambda cid: Outcome.ok("b", correlation_id=cid),
            ),
        ]
    )
    assert result.succeeded
    assert result.first_failure() is None
    assert len(result.records) == 2
    assert all(
        record.correlation_id == result.correlation_id for record in result.records
    )
    assert all(record.status is StageStatus.SUCCEEDED for record in result.records)
    assert all(record.started_at is not None for record in result.records)


def test_failure_stops_pipeline_and_skips_later_stages():
    pipeline = ProcessingPipeline()

    def failing_stage(cid: str) -> Outcome[object]:
        raise InputError("corrupt drawing", remediation="re-export")

    result = pipeline.execute(
        [
            (PipelineStage.INTERPRETATION, failing_stage),
            (
                PipelineStage.ASSET_DERIVATION,
                lambda cid: Outcome.ok("never runs"),
            ),
        ],
        correlation_id="cid-fixed",
    )
    assert not result.succeeded
    assert result.correlation_id == "cid-fixed"
    failure = result.first_failure()
    assert failure is not None
    assert failure.stage is PipelineStage.INTERPRETATION
    assert failure.error_code == "INPUT_ERROR"
    assert result.records[1].status is StageStatus.SKIPPED


def test_unexpected_exceptions_hit_the_stage_error_boundary():
    pipeline = ProcessingPipeline()

    def broken_stage(cid: str) -> Outcome[object]:
        raise RuntimeError("segfault-adjacent")

    result = pipeline.execute([(PipelineStage.VALIDATION, broken_stage)])
    failure = result.first_failure()
    assert failure is not None
    assert failure.error_code == "PROCESSING_ERROR"
    assert "segfault-adjacent" in failure.message
