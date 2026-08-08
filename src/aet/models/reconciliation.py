"""Reconciliation of drawing-derived assets against a registry (SDS-011).

Pure domain logic: a comparison over :class:`~aet.models.asset.Asset` records
with no engine machinery and no I/O. It lives in the domain layer so both the
asset engine and the validation engine can depend on it without depending on
each other, which SDS-002 §6.2 does not permit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aet.core.errors import ProcessingError
from aet.models.asset import Asset

#: Metres two positions may differ by and still be considered the same asset.
#: Survey and registry coordinates for one fitting agree closely; a project
#: with looser survey practice should raise this.
DEFAULT_POSITION_TOLERANCE_M = 1.0


@dataclass(frozen=True, slots=True)
class AssetPair:
    """One drawing asset matched to one registry asset by name."""

    name: str
    drawing: Asset
    registry: Asset
    #: Separation in metres, or ``None`` when the two cannot be compared —
    #: either lacks a coordinate, or they state different UTM zones.
    distance: float | None = None


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """The result of comparing a drawing against a registry (SDS-011 §6).

    ``type_mismatches``, ``position_mismatches``, and ``unchecked_positions``
    are **subsets of** ``matched``: a pair the two sources disagree about is
    still the same asset. Reading them as disjoint buckets would double-count.
    """

    drawing_total: int = 0
    registry_total: int = 0
    matched: list[AssetPair] = field(default_factory=list)
    type_mismatches: list[AssetPair] = field(default_factory=list)
    position_mismatches: list[AssetPair] = field(default_factory=list)
    unchecked_positions: list[AssetPair] = field(default_factory=list)
    missing_from_registry: list[Asset] = field(default_factory=list)
    missing_from_drawing: list[Asset] = field(default_factory=list)
    ambiguous_names: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        """Whether both sides were present, so a comparison means anything."""
        return bool(self.drawing_total and self.registry_total)


def is_drawing_asset(asset: Asset) -> bool:
    """Whether an asset came from a drawing rather than a registry.

    Provenance, not a flag: a derived asset carries the snapshot it came from
    (SDS-010 §7.4), while a registry import leaves ``snapshot_id`` empty
    (SDS-004 §5.4).
    """
    return bool(asset.snapshot_id)


def partition_by_provenance(
    assets: list[Asset],
) -> tuple[list[Asset], list[Asset]]:
    """Split assets into ``(drawing, registry)`` by their provenance."""
    drawing = [asset for asset in assets if is_drawing_asset(asset)]
    registry = [asset for asset in assets if not is_drawing_asset(asset)]
    return drawing, registry


def match_key(name: str) -> str:
    """Normalize an asset name for matching (SDS-011 §5.2).

    Trimmed and case-folded: AGL tags are conventionally upper case, and a
    tag differing only in case is the same tag recorded inconsistently, not a
    different asset.
    """
    return name.strip().casefold()


def reconcile(
    drawing_assets: list[Asset],
    registry_assets: list[Asset],
    *,
    position_tolerance_m: float = DEFAULT_POSITION_TOLERANCE_M,
) -> Reconciliation:
    """Compare drawing-derived assets against registry-imported assets."""
    drawing_index = _index_by_name(drawing_assets)
    registry_index = _index_by_name(registry_assets)

    # A name appearing more than once on either side cannot be matched to a
    # single counterpart. Report it rather than picking one (SDS-011 §5.3).
    ambiguous = sorted(
        key
        for key, group in {**drawing_index, **registry_index}.items()
        if len(drawing_index.get(key, ())) > 1 or len(registry_index.get(key, ())) > 1
    )
    ambiguous_keys = set(ambiguous)

    matched: list[AssetPair] = []
    type_mismatches: list[AssetPair] = []
    position_mismatches: list[AssetPair] = []
    unchecked: list[AssetPair] = []
    missing_from_registry: list[Asset] = []
    missing_from_drawing: list[Asset] = []

    for key, group in drawing_index.items():
        if key in ambiguous_keys:
            continue
        counterparts = registry_index.get(key)
        if not counterparts:
            missing_from_registry.append(group[0])
            continue
        pair = _pair(group[0], counterparts[0])
        matched.append(pair)
        if pair.drawing.asset_type != pair.registry.asset_type:
            type_mismatches.append(pair)
        if pair.distance is None:
            unchecked.append(pair)
        elif pair.distance > position_tolerance_m:
            position_mismatches.append(pair)

    for key, group in registry_index.items():
        if key in ambiguous_keys or key in drawing_index:
            continue
        missing_from_drawing.append(group[0])

    return Reconciliation(
        drawing_total=len(drawing_assets),
        registry_total=len(registry_assets),
        matched=matched,
        type_mismatches=type_mismatches,
        position_mismatches=position_mismatches,
        unchecked_positions=unchecked,
        missing_from_registry=missing_from_registry,
        missing_from_drawing=missing_from_drawing,
        ambiguous_names=[
            _display_name(key, drawing_index, registry_index) for key in ambiguous
        ],
    )


def _index_by_name(assets: list[Asset]) -> dict[str, list[Asset]]:
    index: dict[str, list[Asset]] = {}
    for asset in assets:
        index.setdefault(match_key(asset.name), []).append(asset)
    return index


def _display_name(
    key: str,
    drawing_index: dict[str, list[Asset]],
    registry_index: dict[str, list[Asset]],
) -> str:
    """The name as it was actually recorded, for a normalized key."""
    group = drawing_index.get(key) or registry_index.get(key) or []
    return group[0].name if group else key


def _pair(drawing: Asset, registry: Asset) -> AssetPair:
    return AssetPair(
        name=drawing.name,
        drawing=drawing,
        registry=registry,
        distance=_separation(drawing, registry),
    )


def _separation(drawing: Asset, registry: Asset) -> float | None:
    """Metres between two assets, or None when they cannot be compared."""
    if drawing.location is None or registry.location is None:
        return None
    try:
        return drawing.location.distance_to(registry.location)
    except ProcessingError:
        # Different stated UTM zones. Not a mismatch to report as a distance —
        # the two positions are simply not comparable (SDS-011 §5.4).
        return None
