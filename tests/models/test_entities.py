"""Tests for domain entity identity and provenance (SDS-002 §9)."""

from datetime import UTC

from aet.models.asset import Asset, AssetRelation
from aet.models.drawing import DrawingSnapshot
from aet.models.project import Project, SourceInput
from aet.models.report import Report
from aet.models.validation import Severity, ValidationResult, ValidationRun


def test_entities_get_stable_unique_identifiers():
    first, second = Project(name="A"), Project(name="B")
    assert first.project_id
    assert second.project_id
    assert first.project_id != second.project_id


def test_timestamps_are_timezone_aware():
    project = Project(name="A")
    assert project.created_at.tzinfo is UTC


def test_source_input_keeps_provenance_fields():
    source = SourceInput(
        project_id="p1",
        path="/data/apron.dwg",
        file_hash="abc123",
        provenance="filesystem:/data/apron.dwg",
    )
    assert source.file_hash == "abc123"
    assert source.file_version == 1
    assert source.provenance.startswith("filesystem:")


def test_derived_artifacts_reference_their_sources():
    snapshot = DrawingSnapshot(project_id="p1", source_input_id="s1")
    asset = Asset(
        project_id="p1",
        snapshot_id=snapshot.snapshot_id,
        asset_type="edge-light",
        name="EL-001",
        source_entity_ids=["e1", "e2"],
    )
    relation = AssetRelation(
        relation_type="feeds",
        from_asset_id=asset.asset_id,
        to_asset_id="other",
    )
    assert asset.snapshot_id == snapshot.snapshot_id
    assert asset.source_entity_ids == ["e1", "e2"]
    assert relation.from_asset_id == asset.asset_id


def test_validation_and_report_models_hold_traceable_fields():
    run = ValidationRun(project_id="p1", rule_ids=["r1"])
    result = ValidationResult(
        rule_id="r1",
        severity=Severity.WARNING,
        passed=False,
        message="Spacing exceeds limit",
        run_id=run.run_id,
        evidence={"asset": "EL-001"},
    )
    report = Report(project_id="p1", report_type="project-summary")
    assert result.run_id == run.run_id
    assert result.evidence["asset"] == "EL-001"
    assert report.version == 1
