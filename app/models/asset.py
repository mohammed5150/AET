"""Engineering asset domain models (SDS-002 §8.6, §9.2.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.geometry import Coordinate
from app.utils.ids import new_id, utc_now


@dataclass(slots=True)
class Asset:
    """A derived engineering asset with provenance to its source entities.

    ``location`` is ``None`` when the source gave no usable position; it is
    numeric when known, so spatial rules can measure it (SDS-009 §5.1).
    """

    project_id: str
    snapshot_id: str
    asset_type: str
    name: str
    location: Coordinate | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    source_entity_ids: list[str] = field(default_factory=list)
    asset_id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AssetRelation:
    """A typed relationship between two derived assets."""

    relation_type: str
    from_asset_id: str
    to_asset_id: str
    relation_id: str = field(default_factory=new_id)
