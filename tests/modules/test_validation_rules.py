"""Tests for the SDS-005 standard rule pack."""

from aet.models.asset import Asset
from aet.models.drawing import DrawingLayer, DrawingSnapshot
from aet.models.geometry import Coordinate
from aet.models.project import Project
from aet.models.validation import Severity
from aet.modules.validation_engine import ValidationContext, standard_rules
from aet.modules.validation_engine.rules import (
    SAMPLE_LIMIT,
    AssetClassificationRule,
    AssetLocationRule,
    DuplicateAssetNameRule,
    EmptyLayersRule,
    SkippedEntitiesRule,
)


def _asset(name: str, asset_type: str = "light-fitting", located: bool = True):
    return Asset(
        project_id="p1",
        snapshot_id="",
        asset_type=asset_type,
        name=name,
        location=(
            Coordinate(easting=1.0, northing=2.0, zone="40 N") if located else None
        ),
    )


def _context(assets=(), snapshots=()):
    return ValidationContext(
        project=Project(name="Test"),
        assets=list(assets),
        snapshots=list(snapshots),
    )


def test_location_rule_passes_and_fails():
    [passed] = AssetLocationRule().evaluate(_context([_asset("A.1")]))
    assert passed.passed
    assert passed.severity is Severity.INFO

    [failed] = AssetLocationRule().evaluate(
        _context([_asset("A.1"), _asset("B.1", located=False)])
    )
    assert not failed.passed
    assert failed.severity is Severity.WARNING
    assert failed.evidence["count"] == "1"
    assert "B.1" in failed.evidence["samples"]


def test_classification_rule_flags_other():
    [failed] = AssetClassificationRule().evaluate(
        _context([_asset("A.1"), _asset("X.1", asset_type="other")])
    )
    assert not failed.passed
    assert failed.evidence["samples"] == "X.1"


def test_duplicate_names_rule_is_error_severity():
    [failed] = DuplicateAssetNameRule().evaluate(
        _context([_asset("A.1"), _asset("A.1"), _asset("B.1")])
    )
    assert not failed.passed
    assert failed.severity is Severity.ERROR
    assert "A.1 (x2)" in failed.evidence["samples"]

    [passed] = DuplicateAssetNameRule().evaluate(
        _context([_asset("A.1"), _asset("B.1")])
    )
    assert passed.passed


def test_skipped_entities_rule_reads_snapshot_metadata():
    clean = DrawingSnapshot(
        project_id="p1",
        source_input_id="s1",
        metadata={"skipped_entities": "0", "source_path": "a.dxf"},
    )
    dirty = DrawingSnapshot(
        project_id="p1",
        source_input_id="s2",
        metadata={"skipped_entities": "3", "source_path": "b.dxf"},
    )
    [passed] = SkippedEntitiesRule().evaluate(_context(snapshots=[clean]))
    assert passed.passed
    [failed] = SkippedEntitiesRule().evaluate(_context(snapshots=[clean, dirty]))
    assert not failed.passed
    assert "b.dxf (3 skipped)" in failed.evidence["samples"]


def test_empty_layers_rule_is_info_severity():
    snapshot = DrawingSnapshot(
        project_id="p1",
        source_input_id="s1",
        layers=[DrawingLayer("AGL-EDGE", 5), DrawingLayer("EMPTY", 0)],
        metadata={"source_path": "a.dxf"},
    )
    [failed] = EmptyLayersRule().evaluate(_context(snapshots=[snapshot]))
    assert not failed.passed
    assert failed.severity is Severity.INFO
    assert "a.dxf:EMPTY" in failed.evidence["samples"]


def test_evidence_samples_are_capped():
    assets = [_asset(f"A.{i}", located=False) for i in range(SAMPLE_LIMIT + 5)]
    [failed] = AssetLocationRule().evaluate(_context(assets))
    assert failed.evidence["count"] == str(SAMPLE_LIMIT + 5)
    assert len(failed.evidence["samples"].split(", ")) == SAMPLE_LIMIT


def test_rules_with_nothing_to_check_pass():
    for rule in standard_rules():
        [finding] = rule.evaluate(_context())
        assert finding.passed, rule.rule_id
