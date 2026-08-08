"""Tests for SDS-012: AGL engineering validation rules."""

import pytest

from aet.models.asset import Asset
from aet.models.electrical import parse_load_watts, parse_regulator_rating_kva
from aet.models.geometry import Coordinate
from aet.models.project import Project
from aet.models.validation import Severity, ValidationResult
from aet.modules.validation_engine import ValidationContext, standard_rules
from aet.modules.validation_engine.agl_rules import (
    EXAMPLE_SPACING_LIMITS,
    AssetSpacingRule,
    CircuitLoadRule,
    SpacingLimit,
    agl_engineering_rules,
)


def _fitting(
    name: str,
    circuit: str = "TCC102",
    family: str = "TCC",
    northing: float | None = 0.0,
    asset_class: str = "ADB-BI-GG-S-INSET-8IN-2x40W",
    zone: str = "40 N",
) -> Asset:
    attributes = {"circuit": circuit, "circuit_family": family}
    if asset_class:
        attributes["asset_class"] = asset_class
    return Asset(
        project_id="p1",
        snapshot_id="snap-1",
        asset_type="light-fitting",
        name=name,
        location=(
            None
            if northing is None
            else Coordinate(easting=0.0, northing=northing, zone=zone)
        ),
        attributes=attributes,
    )


def _context(assets: list[Asset]) -> ValidationContext:
    return ValidationContext(project=Project(name="Test"), assets=assets)


def _by_rule(results: list[ValidationResult], rule_id: str) -> ValidationResult:
    return next(result for result in results if result.rule_id == rule_id)


# -- §9.1-2 electrical parsing ---------------------------------------------


@pytest.mark.parametrize(
    ("designation", "expected"),
    [
        ("ADB-BI-GG-S-INSET-8IN-2x40W", 80.0),
        ("ADB-UNI-C-ELEV-150W", 150.0),
        ("CCH-OMNI-B-INSET-8IN-48W", 48.0),
        ("ADB-3x25W", 75.0),
        ("ADB-2X40W", 80.0),
        ("ADB-12.5W", 12.5),
    ],
)
def test_load_is_parsed_from_the_class_designation(designation, expected):
    assert parse_load_watts(designation) == pytest.approx(expected)


def test_the_multiplied_form_wins_over_the_single_form():
    # "2x40W" contains "40W"; the naive order would read 80 W as 40 W.
    assert parse_load_watts("INSET-8IN-2x40W") == pytest.approx(80.0)


@pytest.mark.parametrize("designation", ["AGL PIT", "SGN", "", "ADB-8IN"])
def test_a_designation_stating_no_load_parses_to_none(designation):
    assert parse_load_watts(designation) is None


@pytest.mark.parametrize(
    ("designation", "expected"),
    [("CCR-CRE-30KVA", 30.0), ("CCR-CCH-7.5KVA", 7.5), ("ccr-15kva", 15.0)],
)
def test_regulator_rating_is_parsed(designation, expected):
    assert parse_regulator_rating_kva(designation) == pytest.approx(expected)


def test_a_fitting_has_no_regulator_rating():
    assert parse_regulator_rating_kva("ADB-BI-GG-S-INSET-8IN-2x40W") is None


# -- §9.3 unconfigured means unchecked, never silently passing -------------


def test_spacing_with_no_limits_checks_nothing_and_says_so():
    [finding] = AssetSpacingRule().evaluate(
        _context([_fitting("A.1", northing=0.0), _fitting("A.2", northing=500.0)])
    )
    assert finding.passed
    assert finding.severity is Severity.INFO
    assert "No spacing limits are configured" in finding.message


# -- §9.4 spacing breaches --------------------------------------------------


def test_a_gap_beyond_the_maximum_is_flagged():
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    results = AssetSpacingRule(limits).evaluate(
        _context([_fitting("A.1", northing=0.0), _fitting("A.2", northing=60.0)])
    )
    breach = _by_rule(results, "agl.spacing")
    assert not breach.passed
    assert breach.severity is Severity.WARNING
    assert "A.1 (60.0 m, max 31)" in breach.evidence["samples"]


def test_fittings_too_close_together_are_flagged():
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    results = AssetSpacingRule(limits).evaluate(
        _context([_fitting("A.1", northing=0.0), _fitting("A.2", northing=0.5)])
    )
    breach = _by_rule(results, "agl.spacing")
    assert not breach.passed
    assert "min 7" in breach.evidence["samples"]


def test_spacing_within_limits_passes():
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    assets = [_fitting(f"A.{i}", northing=float(i * 15)) for i in range(5)]
    results = AssetSpacingRule(limits).evaluate(_context(assets))
    assert _by_rule(results, "agl.spacing").passed


def test_an_interior_gap_is_not_detected_by_nearest_neighbour():
    """Pins a known limitation of the chosen measure (SDS-012 §5.2).

    With the fitting at 30 m absent, each survivor still has a peer 15 m away
    on its other side, so no separation exceeds the nominal and the rule
    passes. Detecting this needs consecutive ordering along the alignment,
    which the model cannot provide. Asserted so the limit stays visible
    instead of being rediscovered as a bug.
    """
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=20.0)}
    northings = [0.0, 15.0, 45.0, 60.0]  # the fitting at 30 m is absent
    assets = [_fitting(f"A.{i}", northing=n) for i, n in enumerate(northings)]
    breach = _by_rule(
        AssetSpacingRule(limits).evaluate(_context(assets)), "agl.spacing"
    )
    assert breach.passed


def test_an_isolated_fitting_is_detected():
    # What nearest-neighbour does catch: a fitting far from every peer, which
    # usually means it is tagged onto the wrong circuit.
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    northings = [0.0, 15.0, 30.0, 400.0]
    assets = [_fitting(f"A.{i}", northing=n) for i, n in enumerate(northings)]
    breach = _by_rule(
        AssetSpacingRule(limits).evaluate(_context(assets)), "agl.spacing"
    )
    assert not breach.passed
    assert "A.3" in breach.evidence["samples"]


# -- §9.5 what was not checked is reported ---------------------------------


def test_a_family_with_no_limit_is_reported_unchecked():
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    results = AssetSpacingRule(limits).evaluate(
        _context(
            [
                _fitting("S.1", circuit="SBC13L", family="SBC", northing=0.0),
                _fitting("S.2", circuit="SBC13L", family="SBC", northing=3.0),
            ]
        )
    )
    unchecked = _by_rule(results, "agl.spacing.unchecked")
    assert not unchecked.passed
    assert "SBC13L (no limit for its family)" in unchecked.evidence["samples"]


def test_a_circuit_with_one_located_fitting_is_reported_unchecked():
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    results = AssetSpacingRule(limits).evaluate(
        _context([_fitting("A.1", northing=0.0), _fitting("A.2", northing=None)])
    )
    unchecked = _by_rule(results, "agl.spacing.unchecked")
    assert not unchecked.passed
    assert "fewer than two located fittings" in unchecked.evidence["samples"]


def test_incomparable_zones_leave_a_fitting_unchecked():
    # SDS-009 refuses a cross-zone measurement; it must not read as compliant.
    limits = {"TCC": SpacingLimit(min_m=7.0, max_m=31.0)}
    results = AssetSpacingRule(limits).evaluate(
        _context(
            [
                _fitting("A.1", northing=0.0, zone="40 N"),
                _fitting("A.2", northing=15.0, zone="39 N"),
            ]
        )
    )
    unchecked = _by_rule(results, "agl.spacing.unchecked")
    assert not unchecked.passed
    assert "no comparable neighbour" in unchecked.evidence["samples"]
    assert _by_rule(results, "agl.spacing").passed


# -- §9.6-7 circuit load ----------------------------------------------------


def test_load_is_summed_per_circuit_and_compared_to_the_rating():
    # Six 80 W fittings = 480 W against a 400 W rating.
    assets = [_fitting(f"A.{i}") for i in range(6)]
    results = CircuitLoadRule({"TCC102": 400.0}).evaluate(_context(assets))
    overload = _by_rule(results, "agl.circuit-load")
    assert not overload.passed
    assert overload.severity is Severity.ERROR
    assert "TCC102 (480 W of 400 W)" in overload.evidence["samples"]


def test_a_circuit_within_its_rating_passes():
    assets = [_fitting(f"A.{i}") for i in range(3)]
    results = CircuitLoadRule({"TCC102": 400.0}).evaluate(_context(assets))
    assert _by_rule(results, "agl.circuit-load").passed


def test_with_no_ratings_the_load_is_reported_but_not_judged():
    assets = [_fitting(f"A.{i}") for i in range(3)]
    results = CircuitLoadRule().evaluate(_context(assets))
    verdict = _by_rule(results, "agl.circuit-load")
    assert verdict.passed
    assert "No circuit ratings are configured" in verdict.message
    summary = _by_rule(results, "agl.circuit-load.summary")
    assert "TCC102: 240 W" in summary.evidence["loads"]


# -- §9.8 an unread class is never a silent zero ---------------------------


def test_assets_stating_no_load_are_counted_and_reported():
    # Treating these as zero would understate the total and make an overloaded
    # circuit look compliant.
    assets = [_fitting("A.1"), _fitting("PIT.1", asset_class="AGL PIT")]
    results = CircuitLoadRule().evaluate(_context(assets))
    unread = _by_rule(results, "agl.circuit-load.unread")
    assert not unread.passed
    assert unread.severity is Severity.WARNING
    assert "PIT.1" in unread.evidence["samples"]
    assert "A.1" not in unread.evidence["samples"]


def test_an_unread_class_does_not_contribute_to_the_total():
    assets = [_fitting("A.1"), _fitting("PIT.1", asset_class="AGL PIT")]
    summary = _by_rule(
        CircuitLoadRule().evaluate(_context(assets)), "agl.circuit-load.summary"
    )
    assert "TCC102: 80 W" in summary.evidence["loads"]


# -- §9.9 the rules are opt-in ---------------------------------------------


def test_engineering_rules_are_not_in_the_standard_pack():
    # An unconfigured limit is not a check, so these do not ship on by default.
    packed = {rule.rule_id for rule in standard_rules()}
    assert "agl.spacing" not in packed
    assert "agl.circuit-load" not in packed


def test_the_factory_builds_both_rules_configured():
    rules = agl_engineering_rules(
        spacing_limits={"TCC": SpacingLimit(min_m=7.0, max_m=31.0)},
        circuit_ratings_w={"TCC102": 400.0},
    )
    assert [rule.rule_id for rule in rules] == ["agl.spacing", "agl.circuit-load"]
    assets = [_fitting(f"A.{i}", northing=float(i * 15)) for i in range(6)]
    findings = [f for rule in rules for f in rule.evaluate(_context(assets))]
    assert any(not f.passed for f in findings)


# -- §4.1 the example map is opt-in, not a default -------------------------


def test_the_example_limit_map_is_consumed_by_nothing_automatically():
    # It exists so a project has somewhere to start, not so the tool has an
    # opinion about a safety threshold.
    assert EXAMPLE_SPACING_LIMITS
    assert (
        AssetSpacingRule()
        .evaluate(_context([_fitting("A.1")]))[0]
        .message.startswith("No spacing limits")
    )
    configured = AssetSpacingRule(EXAMPLE_SPACING_LIMITS)
    results = configured.evaluate(
        _context([_fitting("A.1", northing=0.0), _fitting("A.2", northing=60.0)])
    )
    assert not _by_rule(results, "agl.spacing").passed
