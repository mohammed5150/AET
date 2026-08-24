"""Tests for the typed coordinate model (SDS-009)."""

import math

import pytest

from aet.core.errors import ProcessingError
from aet.models.geometry import Coordinate, parse_coordinate


def test_distance_is_planar_and_in_metres():
    start = Coordinate(easting=261000.0, northing=2703000.0, zone="40 N")
    end = Coordinate(easting=261030.0, northing=2703040.0, zone="40 N")
    assert start.distance_to(end) == pytest.approx(50.0)
    assert end.distance_to(start) == pytest.approx(50.0)


def test_distance_ignores_elevation():
    start = Coordinate(easting=0.0, northing=0.0, elevation=0.0)
    end = Coordinate(easting=3.0, northing=4.0, elevation=100.0)
    assert start.distance_to(end) == pytest.approx(5.0)


def test_distance_across_utm_zones_is_a_processing_error():
    # A number here would look usable and be meaningless (SDS-009 §5.2).
    start = Coordinate(easting=261000.0, northing=2703000.0, zone="40 N")
    end = Coordinate(easting=261000.0, northing=2703000.0, zone="39 N")
    with pytest.raises(ProcessingError) as raised:
        start.distance_to(end)
    assert "40 N" in str(raised.value)
    assert "39 N" in str(raised.value)
    assert raised.value.remediation


@pytest.mark.parametrize(
    ("first_zone", "second_zone"),
    [
        ("40 N", "40N"),
        ("40N", "40n"),
        ("40 N", "40n"),
        ("40N", " 40N "),
    ],
)
def test_distance_treats_equivalently_formatted_zones_as_the_same_zone(
    first_zone, second_zone
):
    # Different sources format the same zone differently; the comparison
    # must not raise a cross-zone error between them (SDS-009 §5.2).
    start = Coordinate(easting=261000.0, northing=2703000.0, zone=first_zone)
    end = Coordinate(easting=261030.0, northing=2703040.0, zone=second_zone)
    assert start.distance_to(end) == pytest.approx(50.0)


def test_distance_allows_an_unknown_zone_on_either_side():
    start = Coordinate(easting=0.0, northing=0.0)
    end = Coordinate(easting=3.0, northing=4.0, zone="40 N")
    assert start.distance_to(end) == pytest.approx(5.0)


def test_coordinates_are_immutable_and_comparable():
    first = Coordinate(easting=1.0, northing=2.0, zone="40 N")
    assert first == Coordinate(easting=1.0, northing=2.0, zone="40 N")
    assert first != Coordinate(easting=1.0, northing=2.0, zone="39 N")
    with pytest.raises(AttributeError):
        first.easting = 5.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("easting", "northing"),
    [
        ("261833.45", "2703563.93"),
        (261833.45, 2703563.93),
        ("  261833.45  ", "  2703563.93  "),
    ],
)
def test_parse_accepts_survey_text_and_numbers(easting, northing):
    parsed = parse_coordinate(easting, northing, zone=" 40 N ")
    assert parsed == Coordinate(easting=261833.45, northing=2703563.93, zone="40 N")


@pytest.mark.parametrize(
    ("easting", "northing"),
    [
        (None, None),
        ("", ""),
        ("261833.45", None),
        (None, "2703563.93"),
        ("261833.45", ""),
        ("not-a-number", "2703563.93"),
        ("261833.45", "N/A"),
        (True, False),
    ],
)
def test_parse_returns_none_when_either_ordinate_is_unusable(easting, northing):
    # Both ordinates are required: a half-known position is not a position.
    assert parse_coordinate(easting, northing) is None


def test_parse_treats_elevation_as_optional():
    with_elevation = parse_coordinate("1", "2", elevation="12.5")
    assert with_elevation is not None
    assert with_elevation.elevation == pytest.approx(12.5)

    # An unusable elevation must not discard a known planar position.
    without = parse_coordinate("1", "2", elevation="unknown")
    assert without is not None
    assert without.elevation is None


def test_parse_defaults_the_zone_to_empty():
    parsed = parse_coordinate("1", "2")
    assert parsed is not None
    assert parsed.zone == ""
    assert parse_coordinate("1", "2", zone=None) == parsed


def test_parse_rejects_non_finite_ordinates_as_numbers_not_positions():
    # float() accepts "nan"/"inf"; a distance to them is never meaningful.
    for value in ("nan", "inf", "-inf"):
        parsed = parse_coordinate(value, "2")
        assert parsed is None, f"{value!r} should not become a position"


def test_parsed_positions_measure_against_each_other():
    first = parse_coordinate("261000", "2703000", zone="40 N")
    second = parse_coordinate("261000", "2703100", zone="40 N")
    assert first is not None
    assert second is not None
    assert first.distance_to(second) == pytest.approx(100.0)
    assert not math.isnan(first.distance_to(second))
