"""DXF interpretation via ezdxf (SDS-003 §5, §6; SDS-008).

Converts DXF modelspace entities into the normalized drawing model.
File-level read failures raise :class:`InputError`; entity-level failures
are skipped and counted per SDS-003 §6.2.

Block references carry the engineering payload in AGL drawings, so their
ATTRIB values are captured alongside the block name, and references whose
content this reader cannot see — external references and block definitions
containing nested references — are recorded rather than passed over in
silence (SDS-008).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import ezdxf
from ezdxf.lldxf.const import DXFError

from app.core.errors import InputError
from app.core.logging import StructuredLogger, get_logger
from app.models.drawing import DrawingEntity, DrawingLayer, DrawingSnapshot
from app.models.project import SourceInput

BLOCK_ATTRIBUTE_PREFIX = "attr."


def _xy(point) -> list[float]:
    return [float(point[0]), float(point[1])]


@dataclass(frozen=True, slots=True)
class _BlockFacts:
    """What one block definition tells us about references to it."""

    is_xref: bool
    nested_inserts: int


class DxfInterpreter:
    """Built-in interpreter for the DXF format (SDS-003 §3)."""

    supported_formats = ("dxf",)

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger or get_logger("dxf-interpreter")

    def interpret(self, source: SourceInput) -> DrawingSnapshot:
        try:
            document = ezdxf.readfile(source.path)
        except (OSError, DXFError) as exc:
            raise InputError(
                f"Failed to read DXF file {source.path}: {exc}",
                remediation=("Verify the file is a valid DXF export and re-import it."),
            ) from exc

        blocks = self._block_facts(document)
        entities: list[DrawingEntity] = []
        skipped = 0
        for raw in document.modelspace():
            handle = getattr(raw.dxf, "handle", None)
            try:
                entity = self._convert(raw, blocks)
            except Exception as exc:  # noqa: BLE001 - skip per SDS-003 §6.2
                skipped += 1
                self._logger.warn(
                    f"Skipped entity {handle}: {exc}",
                    stage="interpretation",
                    project_id=source.project_id,
                )
                continue
            if entity is None:
                skipped += 1
                self._logger.debug(
                    f"Unsupported entity type {raw.dxftype()} ({handle})",
                    stage="interpretation",
                    project_id=source.project_id,
                )
                continue
            entities.append(entity)

        unresolved = self._unresolved_references(entities)
        per_layer = Counter(entity.layer for entity in entities)
        layer_names = {layer.dxf.name for layer in document.layers}
        layer_names.update(per_layer)
        layers = [
            DrawingLayer(name=name, entity_count=per_layer.get(name, 0))
            for name in sorted(layer_names)
        ]
        return DrawingSnapshot(
            project_id=source.project_id,
            source_input_id=source.input_id,
            layers=layers,
            entities=entities,
            metadata={
                "source_path": source.path,
                "source_hash": source.file_hash,
                "dxf_version": document.dxfversion,
                "units": str(document.header.get("$INSUNITS", 0)),
                "entity_count": str(len(entities)),
                "skipped_entities": str(skipped),
                "xref_references": str(unresolved["xref"]),
                "nested_block_references": str(unresolved["nested"]),
            },
        )

    def _block_facts(self, document) -> dict[str, _BlockFacts]:
        """Index block definitions once, not once per reference.

        A drawing can hold tens of thousands of block references, so the
        per-definition facts are resolved a single time up front.
        """
        facts: dict[str, _BlockFacts] = {}
        for block in document.blocks:
            nested = sum(1 for entity in block if entity.dxftype() == "INSERT")
            facts[block.name] = _BlockFacts(
                is_xref=bool(block.block_record.is_xref),
                nested_inserts=nested,
            )
        return facts

    @staticmethod
    def _unresolved_references(entities: list[DrawingEntity]) -> dict[str, int]:
        """Count references whose content this reader could not see."""
        return {
            "xref": sum(
                1 for entity in entities if "block_is_xref" in entity.attributes
            ),
            "nested": sum(
                1 for entity in entities if "block_nested_inserts" in entity.attributes
            ),
        }

    def _convert(
        self, raw, blocks: dict[str, _BlockFacts] | None = None
    ) -> DrawingEntity | None:
        entity_type = raw.dxftype().lower()
        attributes: dict[str, str] = {}
        if entity_type == "line":
            geometry: dict[str, object] = {
                "points": [_xy(raw.dxf.start), _xy(raw.dxf.end)]
            }
        elif entity_type == "lwpolyline":
            geometry = {
                "points": [_xy(p) for p in raw.get_points("xy")],
                "closed": bool(raw.closed),
            }
        elif entity_type == "polyline":
            geometry = {
                "points": [_xy(v.dxf.location) for v in raw.vertices],
                "closed": bool(raw.is_closed),
            }
        elif entity_type == "circle":
            geometry = {
                "center": _xy(raw.dxf.center),
                "radius": float(raw.dxf.radius),
            }
        elif entity_type == "arc":
            geometry = {
                "center": _xy(raw.dxf.center),
                "radius": float(raw.dxf.radius),
                "start_angle": float(raw.dxf.start_angle),
                "end_angle": float(raw.dxf.end_angle),
            }
        elif entity_type == "insert":
            geometry = {
                "position": _xy(raw.dxf.insert),
                "rotation": float(raw.dxf.rotation),
            }
            block_name = str(raw.dxf.name)
            attributes["name"] = block_name
            attributes.update(self._block_attributes(raw))
            facts = (blocks or {}).get(block_name)
            if facts is not None:
                # Neither case is interpreted here; both are recorded so a
                # reference whose content is invisible cannot be mistaken for
                # an empty one downstream (SDS-008 §6).
                if facts.is_xref:
                    attributes["block_is_xref"] = "true"
                if facts.nested_inserts:
                    attributes["block_nested_inserts"] = str(facts.nested_inserts)
        elif entity_type == "text":
            geometry = {"position": _xy(raw.dxf.insert)}
            attributes["content"] = str(raw.dxf.text)
        elif entity_type == "mtext":
            geometry = {"position": _xy(raw.dxf.insert)}
            attributes["content"] = str(raw.text)
        elif entity_type == "point":
            geometry = {"position": _xy(raw.dxf.location)}
        else:
            return None
        return DrawingEntity(
            entity_type=entity_type,
            layer=str(raw.dxf.layer),
            attributes=attributes,
            geometry=geometry,
            geometry_ref=str(raw.dxf.handle),
        )

    @staticmethod
    def _block_attributes(raw) -> dict[str, str]:
        """Capture block ATTRIB values, namespaced to keep keys unambiguous.

        Tags come from the drawing, so they are prefixed rather than merged
        into the entity's own keys: a block tagged ``NAME`` must not overwrite
        the block name (SDS-008 §5.1).
        """
        values: dict[str, str] = {}
        for attrib in raw.attribs:
            tag = str(attrib.dxf.tag).strip()
            if tag:
                values[f"{BLOCK_ATTRIBUTE_PREFIX}{tag}"] = str(attrib.dxf.text)
        return values
