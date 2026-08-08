"""Surveyed coordinate model (SDS-009).

Asset positions are numeric so spatial rules can measure them directly.
Registry exports carry coordinates as text, so building one is fallible: an
absent or unusable ordinate yields no coordinate at all rather than a
plausible-looking wrong one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from aet.core.errors import ProcessingError


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A surveyed position within one UTM zone, in metres."""

    easting: float
    northing: float
    zone: str = ""
    elevation: float | None = None

    def distance_to(self, other: Coordinate) -> float:
        """Planar distance in metres, ignoring elevation.

        A distance between two different UTM zones has no meaning, so a
        cross-zone measurement raises rather than returning a number that
        looks usable (SDS-009 §5.2).
        """
        if self.zone and other.zone and self.zone != other.zone:
            raise ProcessingError(
                f"Cannot measure a distance between UTM zones "
                f"'{self.zone}' and '{other.zone}'",
                remediation="Re-project both assets into a single UTM zone.",
            )
        return math.dist((self.easting, self.northing), (other.easting, other.northing))


def parse_coordinate(
    easting: object,
    northing: object,
    zone: object = "",
    elevation: object = None,
) -> Coordinate | None:
    """Build a coordinate from survey values, or ``None`` when unusable.

    Both ordinates are required: either one missing or unparsable makes the
    position unknown. Elevation is optional, so an unusable elevation leaves
    it unset instead of discarding the whole coordinate (SDS-009 §5.3).
    """
    parsed_easting = _number(easting)
    parsed_northing = _number(northing)
    if parsed_easting is None or parsed_northing is None:
        return None
    return Coordinate(
        easting=parsed_easting,
        northing=parsed_northing,
        zone="" if zone is None else str(zone).strip(),
        elevation=_number(elevation),
    )


def _number(value: object) -> float | None:
    """Parse one survey value, treating anything unusable as absent.

    Blank and non-numeric text are absent, and so are the non-finite values
    ``float()`` happily accepts: a NaN ordinate would propagate silently
    through every distance comparison instead of failing where it is read.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return number if math.isfinite(number) else None
