"""AGL engineering validation rules (SDS-012).

These rules check the airfield, not the import: how far apart fittings sit on
a circuit, and how much load a circuit carries. Both are expressible only
because assets now carry measurable positions (SDS-009) and circuit
attributes derived identically from drawings and registries (SDS-010).

**No regulatory limit is shipped as a default.** Spacing and loading limits
come from ICAO Annex 14, the aerodrome's own design standards, and the
approach category of the surface concerned; they are not one number, and a
tool asserting one from memory would be asserting a safety threshold it
cannot vouch for. Both rules therefore check nothing until limits are
configured, and report every group they did not check (SDS-012 §4).
"""

from __future__ import annotations

from dataclasses import dataclass

from aet.core.errors import ProcessingError
from aet.models.asset import Asset
from aet.models.electrical import parse_load_watts
from aet.models.geometry import Coordinate
from aet.models.validation import Severity, ValidationResult
from aet.modules.validation_engine.engine import ValidationContext, ValidationRule
from aet.modules.validation_engine.rules import SAMPLE_LIMIT, aggregated_finding

CIRCUIT_FAMILY_ATTRIBUTE = "circuit_family"
CIRCUIT_ATTRIBUTE = "circuit"
ASSET_CLASS_ATTRIBUTE = "asset_class"


@dataclass(frozen=True, slots=True)
class SpacingLimit:
    """Permitted separation between adjacent fittings on a circuit family."""

    min_m: float
    max_m: float


#: Illustrative only — **verify before use**. These are plausible starting
#: values for the circuit families the AUH and ZIA registries use, not an
#: authority on Annex 14. Real limits vary with approach category, curve
#: radius, and the aerodrome's design standards. Nothing consumes this map
#: unless a caller passes it in, deliberately (SDS-012 §4.1).
EXAMPLE_SPACING_LIMITS: dict[str, SpacingLimit] = {
    "TCC": SpacingLimit(min_m=7.0, max_m=31.0),  # taxiway centreline
    "TEC": SpacingLimit(min_m=7.0, max_m=61.0),  # taxiway edge
    "SBC": SpacingLimit(min_m=2.0, max_m=4.0),  # stop bar
    "RCC": SpacingLimit(min_m=7.0, max_m=31.0),  # runway centreline
    "REC": SpacingLimit(min_m=7.0, max_m=61.0),  # runway edge
}


class AssetSpacingRule:
    """Adjacent fittings on a circuit sit within the configured spacing.

    Spacing is measured to each fitting's **nearest neighbour on the same
    circuit**, which needs no ordering along the alignment. A gap of roughly
    twice the nominal spacing indicates a missing fitting; a near-zero gap
    indicates a duplicate. Deriving the true along-alignment order would need
    the centreline geometry, which the model does not represent (SDS-012 §5.2).
    """

    rule_id = "agl.spacing"
    description = "Fittings are spaced within limits for their circuit family"

    def __init__(self, limits: dict[str, SpacingLimit] | None = None) -> None:
        self._limits = dict(limits or {})

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        if not self._limits:
            return [
                _unconfigured(
                    self.rule_id,
                    "No spacing limits are configured, so no spacing was checked",
                )
            ]
        groups = _group_by(context.assets, CIRCUIT_ATTRIBUTE)
        breaches: list[str] = []
        unchecked: list[str] = []
        checked = 0
        for circuit, assets in sorted(groups.items()):
            limit = self._limits.get(_family_of(assets))
            if limit is None:
                unchecked.append(f"{circuit} (no limit for its family)")
                continue
            located = [asset for asset in assets if asset.location is not None]
            if len(located) < 2:
                unchecked.append(f"{circuit} (fewer than two located fittings)")
                continue
            for asset, gap in _nearest_neighbour_gaps(located):
                if gap is None:
                    unchecked.append(f"{asset.name} (no comparable neighbour)")
                    continue
                checked += 1
                if gap < limit.min_m:
                    breaches.append(f"{asset.name} ({gap:.1f} m, min {limit.min_m:g})")
                elif gap > limit.max_m:
                    breaches.append(f"{asset.name} ({gap:.1f} m, max {limit.max_m:g})")
        return [
            aggregated_finding(
                self.rule_id,
                breaches,
                checked,
                Severity.WARNING,
                "Fittings are spaced outside the configured limits",
                "Every checked fitting is spaced within limits",
            ),
            aggregated_finding(
                f"{self.rule_id}.unchecked",
                unchecked,
                len(groups),
                Severity.INFO,
                "Circuits or fittings were not spacing-checked",
                "Every circuit was spacing-checked",
            ),
        ]


class CircuitLoadRule:
    """Connected load per circuit stays within the configured rating.

    Load is summed from the wattage encoded in each fitting's class. A class
    that states no wattage is counted and reported rather than treated as
    zero, because a total built from unread classes understates the real load
    — the direction that matters, since it would make an overloaded circuit
    look compliant (SDS-012 §6.3).
    """

    rule_id = "agl.circuit-load"
    description = "Connected load per circuit is within its rating"

    def __init__(self, ratings_w: dict[str, float] | None = None) -> None:
        #: Maximum connected load in watts, keyed by circuit. Empty means the
        #: rule reports load without judging it.
        self._ratings = dict(ratings_w or {})

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        groups = _group_by(context.assets, CIRCUIT_ATTRIBUTE)
        overloaded: list[str] = []
        unread: list[str] = []
        loads: list[str] = []
        for circuit, assets in sorted(groups.items()):
            total = 0.0
            for asset in assets:
                designation = asset.attributes.get(ASSET_CLASS_ATTRIBUTE, "")
                watts = parse_load_watts(designation)
                if watts is None:
                    unread.append(asset.name)
                else:
                    total += watts
            loads.append(f"{circuit}: {total:.0f} W")
            rating = self._ratings.get(circuit)
            if rating is not None and total > rating:
                overloaded.append(f"{circuit} ({total:.0f} W of {rating:.0f} W)")
        findings = [
            aggregated_finding(
                self.rule_id,
                overloaded,
                len(self._ratings),
                Severity.ERROR,
                "Circuits carry more load than their configured rating",
                (
                    "Every rated circuit is within its rating"
                    if self._ratings
                    else "No circuit ratings are configured, so no load was judged"
                ),
            ),
            aggregated_finding(
                f"{self.rule_id}.unread",
                unread,
                sum(len(group) for group in groups.values()),
                Severity.WARNING,
                "Assets state no load, so their circuit total is understated",
                "Every asset states a load",
            ),
        ]
        if loads:
            findings.append(
                ValidationResult(
                    rule_id=f"{self.rule_id}.summary",
                    severity=Severity.INFO,
                    passed=True,
                    message=f"Connected load computed for {len(loads)} circuit(s)",
                    evidence={"loads": ", ".join(loads[:SAMPLE_LIMIT])},
                )
            )
        return findings


def agl_engineering_rules(
    *,
    spacing_limits: dict[str, SpacingLimit] | None = None,
    circuit_ratings_w: dict[str, float] | None = None,
) -> list[ValidationRule]:
    """The SDS-012 rules, configured with a project's own limits."""
    return [
        AssetSpacingRule(spacing_limits),
        CircuitLoadRule(circuit_ratings_w),
    ]


def _unconfigured(rule_id: str, message: str) -> ValidationResult:
    """A rule that could not run because it was given no limits to run against."""
    return ValidationResult(
        rule_id=rule_id,
        severity=Severity.INFO,
        passed=True,
        message=message,
    )


def _group_by(assets: list[Asset], attribute: str) -> dict[str, list[Asset]]:
    groups: dict[str, list[Asset]] = {}
    for asset in assets:
        value = asset.attributes.get(attribute, "")
        if value:
            groups.setdefault(value, []).append(asset)
    return groups


def _family_of(assets: list[Asset]) -> str:
    for asset in assets:
        family = asset.attributes.get(CIRCUIT_FAMILY_ATTRIBUTE, "")
        if family:
            return family
    return ""


def _nearest_neighbour_gaps(
    assets: list[Asset],
) -> list[tuple[Asset, float | None]]:
    """Each asset paired with the distance to its closest peer.

    Quadratic within one circuit, which is the unit that matters: a circuit
    holds hundreds of fittings, not the tens of thousands a whole airfield
    does, so the total stays well below the square of the asset count.
    """
    gaps: list[tuple[Asset, float | None]] = []
    for index, asset in enumerate(assets):
        location = asset.location
        if location is None:
            gaps.append((asset, None))
            continue
        nearest: float | None = None
        for other_index, other in enumerate(assets):
            if other_index == index or other.location is None:
                continue
            separation = _distance(location, other.location)
            if separation is not None and (nearest is None or separation < nearest):
                nearest = separation
        gaps.append((asset, nearest))
    return gaps


def _distance(first: Coordinate, second: Coordinate) -> float | None:
    try:
        return first.distance_to(second)
    except ProcessingError:
        # Different stated UTM zones; not comparable rather than far apart.
        return None
