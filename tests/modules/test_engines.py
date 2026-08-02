"""Tests for drawing, asset, validation, and reporting engines."""

from app.models.asset import Asset
from app.models.drawing import DrawingSnapshot
from app.models.project import Project, SourceInput
from app.models.report import ReportRequest
from app.models.validation import RunStatus, Severity, ValidationResult
from app.modules.asset_engine import AssetCollection, AssetEngine
from app.modules.drawing_engine import DrawingEngine
from app.modules.reporting_engine import MarkdownFormatter, ReportingEngine
from app.modules.validation_engine import ValidationContext, ValidationEngine


def _source() -> SourceInput:
    return SourceInput(project_id="p1", path="/data/apron.dwg", file_hash="h")


def test_drawing_engine_normalizes_with_provenance():
    source = _source()
    outcome = DrawingEngine().normalize(source, correlation_id="cid-1")
    assert outcome.success
    snapshot = outcome.payload
    assert snapshot is not None
    assert snapshot.source_input_id == source.input_id
    assert snapshot.project_id == source.project_id
    assert snapshot.metadata["source_path"] == "/data/apron.dwg"
    assert snapshot.metadata["source_hash"] == "h"


def test_drawing_engine_wraps_interpreter_failures():
    class BrokenInterpreter:
        def interpret(self, source):
            raise ValueError("bad layer table")

    engine = DrawingEngine(interpreter=BrokenInterpreter())
    outcome = engine.normalize(_source(), correlation_id="cid-2")
    assert not outcome.success
    assert outcome.error_code == "PROCESSING_ERROR"
    assert "bad layer table" in outcome.message


def test_asset_engine_returns_structured_collection():
    snapshot = DrawingSnapshot(project_id="p1", source_input_id="s1")
    outcome = AssetEngine().derive(snapshot, correlation_id="cid-3")
    assert outcome.success
    assert outcome.payload == AssetCollection()


def test_validation_engine_isolates_failing_rules():
    class GoodRule:
        rule_id = "good"
        description = "always passes"

        def evaluate(self, context):
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    severity=Severity.INFO,
                    passed=True,
                    message="ok",
                )
            ]

    class BadRule:
        rule_id = "bad"
        description = "always crashes"

        def evaluate(self, context):
            raise RuntimeError("rule crashed")

    context = ValidationContext(project=Project(name="Test"))
    outcome = ValidationEngine().run(
        context, [GoodRule(), BadRule()], correlation_id="cid-4"
    )
    assert outcome.success
    payload = outcome.payload
    assert payload is not None
    assert payload.run.status is RunStatus.COMPLETED
    assert payload.run.completed_at is not None
    by_rule = {result.rule_id: result for result in payload.results}
    assert by_rule["good"].passed
    assert not by_rule["bad"].passed
    assert "rule crashed" in by_rule["bad"].message
    assert all(r.run_id == payload.run.run_id for r in payload.results)


def test_reporting_engine_composes_and_renders_markdown():
    project = Project(name="Runway 13R")
    snapshot = DrawingSnapshot(project_id=project.project_id, source_input_id="s1")
    asset = Asset(
        project_id=project.project_id,
        snapshot_id=snapshot.snapshot_id,
        asset_type="edge-light",
        name="EL-001",
    )
    finding = ValidationResult(
        rule_id="spacing",
        severity=Severity.WARNING,
        passed=False,
        message="Spacing exceeds limit",
    )
    engine = ReportingEngine()
    view = engine.compose(project, [], [snapshot], [asset], [finding])
    assert view.asset_count == 1
    assert view.findings_by_severity == {"warning": 1}
    request = ReportRequest(
        project_id=project.project_id, report_type="project-summary"
    )
    outcome = engine.generate(
        request, view, [MarkdownFormatter()], correlation_id="cid-5"
    )
    assert outcome.success
    report, artifacts = outcome.payload
    assert report.summary == "1 asset(s), 1 finding(s)"
    assert len(artifacts) == 1
    assert artifacts[0].format_name == "markdown"
    assert "Runway 13R" in artifacts[0].content
    assert "Spacing exceeds limit" in artifacts[0].content


def test_reporting_engine_fails_cleanly_on_formatter_error():
    class BrokenFormatter:
        format_name = "broken"

        def render(self, view):
            raise OSError("disk full")

    project = Project(name="Test")
    engine = ReportingEngine()
    view = engine.compose(project, [], [], [], [])
    request = ReportRequest(
        project_id=project.project_id, report_type="project-summary"
    )
    outcome = engine.generate(request, view, [BrokenFormatter()])
    assert not outcome.success
    assert outcome.error_code == "PROCESSING_ERROR"
