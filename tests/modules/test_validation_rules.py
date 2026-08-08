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
    ReconciliationRule,
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
    assert "A.1 (x2 in registry)" in failed.evidence["samples"]

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


def _drawing_asset(name: str, asset_type: str = "light-fitting", northing: float = 0.0):
    return Asset(
        project_id="p1",
        snapshot_id="snap-1",
        asset_type=asset_type,
        name=name,
        location=Coordinate(easting=0.0, northing=northing, zone="40 N"),
    )


def _registry_asset(
    name: str, asset_type: str = "light-fitting", northing: float = 0.0
):
    return Asset(
        project_id="p1",
        snapshot_id="",
        asset_type=asset_type,
        name=name,
        location=Coordinate(easting=0.0, northing=northing, zone="40 N"),
    )


def _messages(results):
    return [result.message for result in results]


# -- SDS-011 §8.9 not applicable is stated, not implied ---------------------


def test_reconciliation_reports_not_applicable_with_one_side_absent():
    # Every asset would otherwise be reported missing from the absent side,
    # which is noise rather than a finding.
    [finding] = ReconciliationRule().evaluate(
        _context([_registry_asset("A.1"), _registry_asset("A.2")])
    )
    assert finding.passed
    assert finding.severity is Severity.INFO
    assert "not applicable" in finding.message
    assert "0 drawing asset(s)" in finding.message
    assert "2 registry asset(s)" in finding.message


def test_reconciliation_not_applicable_with_no_assets_at_all():
    [finding] = ReconciliationRule().evaluate(_context([]))
    assert finding.passed
    assert "not applicable" in finding.message


# -- SDS-011 §8.10 one finding per category --------------------------------


def test_agreeing_sources_pass_every_category():
    results = ReconciliationRule().evaluate(
        _context([_drawing_asset("A.1"), _registry_asset("A.1")])
    )
    assert len(results) == 6
    assert all(result.passed for result in results)
    assert all(result.rule_id == "agl.reconcile" for result in results)


def test_each_disagreement_is_reported_as_its_own_finding():
    context = _context(
        [
            # matched and agreeing
            _drawing_asset("OK.1"),
            _registry_asset("OK.1"),
            # type disagreement
            _drawing_asset("TYPE.1", asset_type="light-fitting"),
            _registry_asset("TYPE.1", asset_type="sign"),
            # position disagreement, 9 m apart
            _drawing_asset("POS.1", northing=0.0),
            _registry_asset("POS.1", northing=9.0),
            # drawing only
            _drawing_asset("DRAWING_ONLY.1"),
            # registry only
            _registry_asset("REGISTRY_ONLY.1"),
        ]
    )
    results = ReconciliationRule().evaluate(context)
    failed = {result.message: result for result in results if not result.passed}

    assert any("disagree on asset type" in m for m in failed)
    assert any("absent from the registry" in m for m in failed)
    assert any("absent from the drawing" in m for m in failed)
    assert any("m apart" in m for m in failed)

    type_finding = next(r for m, r in failed.items() if "asset type" in m)
    assert type_finding.severity is Severity.ERROR
    assert type_finding.evidence["count"] == "1"
    assert "TYPE.1" in type_finding.evidence["samples"]

    missing = next(r for m, r in failed.items() if "absent from the registry" in m)
    assert missing.severity is Severity.WARNING
    assert "DRAWING_ONLY.1" in missing.evidence["samples"]

    position = next(r for m, r in failed.items() if "m apart" in m)
    assert "POS.1 (9.00 m)" in position.evidence["samples"]


def test_duplicate_names_are_an_error_and_block_matching():
    results = ReconciliationRule().evaluate(
        _context(
            [
                _drawing_asset("DUP.1"),
                _drawing_asset("DUP.1"),
                _registry_asset("DUP.1"),
            ]
        )
    )
    ambiguous = next(r for r in results if "cannot be reconciled" in r.message)
    assert not ambiguous.passed
    assert ambiguous.severity is Severity.ERROR
    assert "DUP.1" in ambiguous.evidence["samples"]


def test_unchecked_positions_are_reported_separately():
    # A position that was never compared must not read as one that agreed.
    drawing = _drawing_asset("A.1")
    drawing.location = None
    results = ReconciliationRule().evaluate(_context([drawing, _registry_asset("A.1")]))
    unchecked = next(
        r for r in results if "could not be compared by position" in r.message
    )
    assert not unchecked.passed
    assert unchecked.severity is Severity.INFO
    assert "A.1" in unchecked.evidence["samples"]


def test_tolerance_is_configurable_on_the_rule():
    context = _context(
        [_drawing_asset("A.1", northing=0.0), _registry_asset("A.1", northing=3.0)]
    )
    strict = ReconciliationRule(position_tolerance_m=1.0).evaluate(context)
    lenient = ReconciliationRule(position_tolerance_m=5.0).evaluate(context)
    assert any(not r.passed and "m apart" in r.message for r in strict)
    assert all(r.passed for r in lenient)


# -- SDS-011 §8.11 the rule ships in the standard pack ---------------------


def test_reconciliation_is_in_the_standard_pack():
    assert "agl.reconcile" in {rule.rule_id for rule in standard_rules()}


# -- SDS-011 §9: duplicates are counted per source, not across the project ---


def test_a_reconciled_pair_is_not_reported_as_a_duplicate():
    # A drawing asset and its registry counterpart share a name by definition.
    # Counting the union would report every successful match as a duplicate,
    # contradicting the reconciliation finding beside it.
    [finding] = DuplicateAssetNameRule().evaluate(
        _context([_drawing_asset("TCC102-01/001"), _registry_asset("TCC102-01/001")])
    )
    assert finding.passed
    assert "unique within each source" in finding.message


def test_duplicates_within_one_source_are_still_reported():
    [finding] = DuplicateAssetNameRule().evaluate(
        _context(
            [
                _drawing_asset("DUP.1"),
                _drawing_asset("DUP.1"),
                _registry_asset("DUP.1"),
            ]
        )
    )
    assert not finding.passed
    assert "DUP.1 (x2 in drawing)" in finding.evidence["samples"]
    assert "in registry" not in finding.evidence["samples"]


def test_case_only_duplicates_agree_with_reconciliation():
    # Flagged here and ambiguous there, rather than passing one and failing the
    # other.
    assets = [_registry_asset("TCC1.1"), _registry_asset("tcc1.1")]
    [duplicate] = DuplicateAssetNameRule().evaluate(_context(assets))
    assert not duplicate.passed
    reconcile_findings = ReconciliationRule().evaluate(
        _context([*assets, _drawing_asset("TCC1.1")])
    )
    ambiguous = next(
        r for r in reconcile_findings if "cannot be reconciled" in r.message
    )
    assert not ambiguous.passed
