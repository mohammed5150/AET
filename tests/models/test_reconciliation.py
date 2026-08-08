"""Tests for SDS-011: drawing / registry reconciliation."""

import pytest

from aet.models.asset import Asset
from aet.models.geometry import Coordinate
from aet.models.reconciliation import (
    is_drawing_asset,
    match_key,
    partition_by_provenance,
    reconcile,
)


def _drawing(
    name: str,
    asset_type: str = "light-fitting",
    position: tuple[float, float] | None = (261800.0, 2703500.0),
    zone: str = "",
) -> Asset:
    return Asset(
        project_id="p1",
        snapshot_id="snap-1",  # provenance: a derived asset carries its snapshot
        asset_type=asset_type,
        name=name,
        location=(
            None
            if position is None
            else Coordinate(easting=position[0], northing=position[1], zone=zone)
        ),
    )


def _registry(
    name: str,
    asset_type: str = "light-fitting",
    position: tuple[float, float] | None = (261800.0, 2703500.0),
    zone: str = "40 N",
) -> Asset:
    return Asset(
        project_id="p1",
        snapshot_id="",  # a registry import leaves this empty
        asset_type=asset_type,
        name=name,
        location=(
            None
            if position is None
            else Coordinate(easting=position[0], northing=position[1], zone=zone)
        ),
    )


# -- §8.1 provenance --------------------------------------------------------


def test_provenance_splits_drawing_from_registry():
    drawing, registry = partition_by_provenance(
        [_drawing("A.1"), _registry("A.1"), _drawing("A.2")]
    )
    assert [a.name for a in drawing] == ["A.1", "A.2"]
    assert [a.name for a in registry] == ["A.1"]
    assert is_drawing_asset(_drawing("X")) is True
    assert is_drawing_asset(_registry("X")) is False


# -- §8.2 matching ----------------------------------------------------------


def test_same_name_matches_and_measures_separation():
    result = reconcile(
        [_drawing("TCC102-01/067", position=(261800.0, 2703500.0))],
        [_registry("TCC102-01/067", position=(261800.3, 2703500.4))],
    )
    assert len(result.matched) == 1
    [pair] = result.matched
    assert pair.name == "TCC102-01/067"
    assert pair.distance == pytest.approx(0.5)
    assert result.missing_from_registry == []
    assert result.missing_from_drawing == []
    assert result.applicable is True


# -- §8.3 name normalization ------------------------------------------------


def test_matching_ignores_case_and_whitespace():
    result = reconcile([_drawing("  tcc102-01/067 ")], [_registry("TCC102-01/067")])
    assert len(result.matched) == 1
    # Reporting keeps the name as it was recorded, so the discrepancy stays
    # visible rather than being normalized away.
    assert result.matched[0].name == "  tcc102-01/067 "


def test_match_key_normalizes():
    assert match_key("  TCC1.1 ") == "tcc1.1"


# -- §8.4 duplicates are reported, never resolved ---------------------------


def test_duplicate_name_is_ambiguous_and_absorbed_by_no_other_count():
    result = reconcile(
        [_drawing("DUP.1"), _drawing("DUP.1"), _drawing("OK.1")],
        [_registry("DUP.1"), _registry("OK.1")],
    )
    assert result.ambiguous_names == ["DUP.1"]
    assert [pair.name for pair in result.matched] == ["OK.1"]
    # The ambiguous name must not be silently counted as missing either way.
    assert result.missing_from_registry == []
    assert result.missing_from_drawing == []


def test_duplicate_on_the_registry_side_is_also_ambiguous():
    result = reconcile([_drawing("DUP.1")], [_registry("DUP.1"), _registry("dup.1")])
    assert result.ambiguous_names == ["DUP.1"]
    assert result.matched == []


# -- §8.5 type disagreement -------------------------------------------------


def test_type_mismatch_is_a_match_and_a_mismatch():
    result = reconcile(
        [_drawing("A.1", asset_type="light-fitting")],
        [_registry("A.1", asset_type="sign")],
    )
    # Subsets, not disjoint buckets: a disputed pair is still the same asset.
    assert len(result.matched) == 1
    assert [pair.name for pair in result.type_mismatches] == ["A.1"]
    assert result.missing_from_registry == []


# -- §8.6 position disagreement --------------------------------------------


def test_separation_beyond_tolerance_is_a_position_mismatch():
    result = reconcile(
        [_drawing("A.1", position=(0.0, 0.0))],
        [_registry("A.1", position=(0.0, 5.0))],
        position_tolerance_m=1.0,
    )
    assert len(result.matched) == 1
    assert [pair.name for pair in result.position_mismatches] == ["A.1"]
    assert result.position_mismatches[0].distance == pytest.approx(5.0)


def test_separation_within_tolerance_is_only_a_match():
    result = reconcile(
        [_drawing("A.1", position=(0.0, 0.0))],
        [_registry("A.1", position=(0.0, 0.4))],
        position_tolerance_m=1.0,
    )
    assert len(result.matched) == 1
    assert result.position_mismatches == []
    assert result.unchecked_positions == []


def test_tolerance_is_configurable():
    args = (
        [_drawing("A.1", position=(0.0, 0.0))],
        [_registry("A.1", position=(0.0, 3.0))],
    )
    assert reconcile(*args, position_tolerance_m=1.0).position_mismatches
    assert not reconcile(*args, position_tolerance_m=5.0).position_mismatches


# -- §8.7 positions that cannot be compared --------------------------------


def test_missing_coordinate_makes_a_pair_unchecked_not_mismatched():
    result = reconcile([_drawing("A.1", position=None)], [_registry("A.1")])
    assert len(result.matched) == 1
    assert [pair.name for pair in result.unchecked_positions] == ["A.1"]
    assert result.position_mismatches == []
    assert result.matched[0].distance is None


def test_conflicting_utm_zones_make_a_pair_unchecked():
    # SDS-009 refuses a cross-zone measurement; a check that never ran must not
    # be reported as a check that passed.
    result = reconcile([_drawing("A.1", zone="39 N")], [_registry("A.1", zone="40 N")])
    assert len(result.matched) == 1
    assert [pair.name for pair in result.unchecked_positions] == ["A.1"]
    assert result.position_mismatches == []


def test_an_unknown_zone_on_one_side_is_still_comparable():
    # The derived side defaults to an unknown zone (SDS-010 §7.2).
    result = reconcile(
        [_drawing("A.1", position=(0.0, 0.0), zone="")],
        [_registry("A.1", position=(0.0, 0.5), zone="40 N")],
    )
    assert result.matched[0].distance == pytest.approx(0.5)
    assert result.unchecked_positions == []


# -- §8.8 missing on either side -------------------------------------------


def test_assets_present_on_only_one_side_are_reported_missing():
    result = reconcile(
        [_drawing("BOTH.1"), _drawing("DRAWING_ONLY.1")],
        [_registry("BOTH.1"), _registry("REGISTRY_ONLY.1")],
    )
    assert [a.name for a in result.missing_from_registry] == ["DRAWING_ONLY.1"]
    assert [a.name for a in result.missing_from_drawing] == ["REGISTRY_ONLY.1"]
    assert [pair.name for pair in result.matched] == ["BOTH.1"]


def test_totals_report_both_input_sizes():
    result = reconcile([_drawing("A.1"), _drawing("A.2")], [_registry("A.1")])
    assert result.drawing_total == 2
    assert result.registry_total == 1


@pytest.mark.parametrize(
    ("drawing", "registry"),
    [([], []), ([_drawing("A.1")], []), ([], [_registry("A.1")])],
)
def test_reconciliation_is_not_applicable_with_one_side_absent(drawing, registry):
    assert reconcile(drawing, registry).applicable is False


def test_the_engineering_question_is_answerable():
    # "The drawing shows 12 fittings on TCC102, the registry lists 10 — which
    # two are missing?"
    drawing = [_drawing(f"TCC102-01/{i:03d}") for i in range(1, 13)]
    registry = [_registry(f"TCC102-01/{i:03d}") for i in range(1, 11)]
    result = reconcile(drawing, registry)
    assert len(result.matched) == 10
    assert [a.name for a in result.missing_from_registry] == [
        "TCC102-01/011",
        "TCC102-01/012",
    ]
    assert result.missing_from_drawing == []
