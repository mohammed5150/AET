"""Asset derivation from normalized drawings (SDS-010).

Block references are the only asset candidates: the surrounding lines, arcs,
and text are geometry and annotation, so counting them would produce a number
that looks like an asset count and is not one (SDS-010 §4).

A reference this reader could not see into — an external reference, or a
container placing further references — is declined rather than guessed at,
using the flags SDS-008 records for exactly that purpose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aet.core.logging import StructuredLogger, get_logger
from aet.models.asset import Asset
from aet.models.drawing import DrawingEntity, DrawingSnapshot
from aet.models.geometry import Coordinate
from aet.modules.asset_engine.engine import AssetCollection
from aet.modules.asset_engine.registry import derive_circuit

STAGE_NAME = "asset-derivation"

BLOCK_ATTRIBUTE_PREFIX = "attr."

#: ATTRIB tags consulted for an asset name, in order (SDS-010 §7.1).
DEFAULT_NAME_TAGS: tuple[str, ...] = ("TAG", "ASSET_TAG", "NAME", "ID")

#: $INSUNITS values that mean "metres or unstated" (SDS-010 §7.2).
_METRIC_UNITS = frozenset({"0", "6", ""})


@dataclass(frozen=True, slots=True)
class DerivationRule:
    """Maps a block reference to an asset type (SDS-010 §6).

    At least one pattern must be set. ``block`` is tried before ``layer``
    across the whole table, because a block name names the thing itself while
    a layer only names where it was drawn.
    """

    asset_type: str
    block: str | None = None
    layer: str | None = None


# Conventions from the AUH and ZIA drawing sets. Deliberately conservative:
# a pattern broad enough to catch every fitting in one project will match a
# north arrow in another, and a phantom asset is worse than a missing one
# because it is not obviously wrong (SDS-010 §6.1).
DEFAULT_DERIVATION_RULES: tuple[DerivationRule, ...] = (
    # Fittings, by block name.
    DerivationRule("light-fitting", block=r"^(TCL|TWE|STB|LIL|RGL|STL|RCL|REL)"),
    DerivationRule("light-fitting", block=r"INSET|ELEV"),
    DerivationRule("sign", block=r"^(SGN|SIGN)"),
    DerivationRule("agl-pit", block=r"^(HH|PIT|HANDHOLE|AGL[_-]?PIT)"),
    DerivationRule("base", block=r"^(NBASE|EBASE|BASE|CRBLK)"),
    DerivationRule("rrm", block=r"^RRM"),
    DerivationRule("ccr", block=r"^CCR"),
    DerivationRule("wdi", block=r"^WDI"),
    DerivationRule("high-mast", block=r"^HIGH[_-]?MAST"),
    DerivationRule("lightpole", block=r"^(LIGHTPOLE|POLE)"),
    # Fittings, by layer, for drawing sets whose blocks are generically named.
    DerivationRule("light-fitting", layer=r"(TCL|TWE|STB|LIL|RGL|STL)"),
    DerivationRule("sign", layer=r"SIGN"),
    DerivationRule("agl-pit", layer=r"(HANDHOLE|AGL[_-]?PIT)"),
    DerivationRule("base", layer=r"(LIGHT[_-]?BASE|CRBLK)"),
)


@dataclass(frozen=True, slots=True)
class DerivationResult:
    """Derived assets together with what was declined, and why (§8)."""

    collection: AssetCollection = field(default_factory=AssetCollection)
    skipped_unclassified: int = 0
    skipped_unresolved: int = 0

    @property
    def derived(self) -> int:
        return len(self.collection.assets)


class DxfAssetExtractor:
    """Derives assets from the block references of a snapshot (SDS-010)."""

    def __init__(
        self,
        rules: tuple[DerivationRule, ...] = DEFAULT_DERIVATION_RULES,
        *,
        utm_zone: str = "",
        name_tags: tuple[str, ...] = DEFAULT_NAME_TAGS,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._rules = rules
        # Not inferred from the drawing: a DXF states coordinates, never the
        # projection they are in (SDS-010 §7.2).
        self._utm_zone = utm_zone.strip()
        self._name_tags = name_tags
        self._logger = logger or get_logger("asset-derivation")

    # -- AssetExtractor contract ------------------------------------------

    def extract(self, snapshot: DrawingSnapshot) -> AssetCollection:
        """Derive assets, discarding the counts (AssetExtractor contract)."""
        return self.derive(snapshot).collection

    def derive(self, snapshot: DrawingSnapshot) -> DerivationResult:
        """Derive assets and report what was declined."""
        units = snapshot.metadata.get("units", "")
        if units not in _METRIC_UNITS:
            # Every downstream distance is in metres; a drawing in millimetres
            # yields positions a thousand times too large (SDS-010 §7.2).
            self._logger.warn(
                f"Drawing units {units!r} are neither metres nor unstated; "
                f"derived coordinates may not be in metres",
                stage=STAGE_NAME,
                project_id=snapshot.project_id,
            )

        assets: list[Asset] = []
        unclassified = 0
        unresolved = 0
        for entity in snapshot.entities:
            if entity.entity_type != "insert":
                continue
            if self._is_unresolved(entity):
                unresolved += 1
                continue
            asset_type = self._classify(entity)
            if asset_type is None:
                unclassified += 1
                continue
            assets.append(self._build(entity, asset_type, snapshot, units))

        self._logger.info(
            f"Derived {len(assets)} asset(s); skipped {unclassified} "
            f"unclassified and {unresolved} unresolved reference(s)",
            stage=STAGE_NAME,
            project_id=snapshot.project_id,
        )
        return DerivationResult(
            collection=AssetCollection(assets=assets),
            skipped_unclassified=unclassified,
            skipped_unresolved=unresolved,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _is_unresolved(entity: DrawingEntity) -> bool:
        """Whether SDS-008 marked this reference's content as unseen."""
        return (
            "block_is_xref" in entity.attributes
            or "block_nested_inserts" in entity.attributes
        )

    def _classify(self, entity: DrawingEntity) -> str | None:
        """The asset type for a reference, or None when no rule matches."""
        block_name = entity.attributes.get("name", "")
        for rule in self._rules:
            if rule.block and re.search(rule.block, block_name, re.IGNORECASE):
                return rule.asset_type
        for rule in self._rules:
            if rule.layer and re.search(rule.layer, entity.layer, re.IGNORECASE):
                return rule.asset_type
        return None

    def _name_for(self, entity: DrawingEntity) -> tuple[str, str]:
        """The asset name and the source it came from (SDS-010 §7.1)."""
        for tag in self._name_tags:
            value = entity.attributes.get(f"{BLOCK_ATTRIBUTE_PREFIX}{tag}", "").strip()
            if value:
                return value, f"attrib:{tag}"
        block_name = entity.attributes.get("name", "block")
        # The DXF handle, not a running counter: stable across re-reads, so
        # re-deriving the same drawing yields the same names.
        return f"{block_name}:{entity.geometry_ref}", "handle"

    @staticmethod
    def _position(entity: DrawingEntity, zone: str) -> Coordinate | None:
        position = entity.geometry.get("position")
        if not isinstance(position, list) or len(position) < 2:
            return None
        easting, northing = position[0], position[1]
        if not isinstance(easting, int | float) or not isinstance(
            northing, int | float
        ):
            return None
        return Coordinate(easting=float(easting), northing=float(northing), zone=zone)

    def _build(
        self,
        entity: DrawingEntity,
        asset_type: str,
        snapshot: DrawingSnapshot,
        units: str,
    ) -> Asset:
        name, name_source = self._name_for(entity)
        attributes = {
            "block_name": entity.attributes.get("name", ""),
            "layer": entity.layer,
            "name_source": name_source,
            "drawing_units": units,
        }
        if entity.geometry_ref:
            attributes["handle"] = entity.geometry_ref
        # Captured ATTRIBs pass through unchanged (SDS-008).
        attributes.update(
            {
                key: value
                for key, value in entity.attributes.items()
                if key.startswith(BLOCK_ATTRIBUTE_PREFIX)
            }
        )
        # Same parser the registry uses, so a drawing asset and a registry
        # asset on one circuit carry identical circuit attributes (SDS-004).
        attributes.update(derive_circuit(name))
        return Asset(
            project_id=snapshot.project_id,
            snapshot_id=snapshot.snapshot_id,
            asset_type=asset_type,
            name=name,
            location=self._position(entity, self._utm_zone),
            attributes=attributes,
            source_entity_ids=[entity.entity_id],
        )
