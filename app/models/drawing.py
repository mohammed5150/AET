"""Normalized drawing domain models (SDS-002 §8.5, §9.2.3).

These models are the format-independent representation produced by the
drawing engine. Format-specific structures never cross this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.utils.ids import new_id, utc_now


@dataclass(slots=True)
class DrawingEntity:
    """A normalized drawing entity with a geometry reference."""

    entity_type: str
    layer: str
    attributes: dict[str, str] = field(default_factory=dict)
    geometry_ref: str | None = None
    entity_id: str = field(default_factory=new_id)


@dataclass(slots=True)
class DrawingLayer:
    """Summary of a normalized drawing layer."""

    name: str
    entity_count: int = 0


@dataclass(slots=True)
class DrawingSnapshot:
    """A normalized, versionable processing snapshot of one source input."""

    project_id: str
    source_input_id: str
    layers: list[DrawingLayer] = field(default_factory=list)
    entities: list[DrawingEntity] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    snapshot_id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)
