"""DXF interpretation via ezdxf (SDS-003 §5, §6).

Converts DXF modelspace entities into the normalized drawing model.
File-level read failures raise :class:`InputError`; entity-level failures
are skipped and counted per SDS-003 §6.2.
"""

from __future__ import annotations

from collections import Counter

import ezdxf
from ezdxf.lldxf.const import DXFError

from app.core.errors import InputError
from app.core.logging import StructuredLogger, get_logger
from app.models.drawing import DrawingEntity, DrawingLayer, DrawingSnapshot
from app.models.project import SourceInput


def _xy(point) -> list[float]:
    return [float(point[0]), float(point[1])]


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

        entities: list[DrawingEntity] = []
        skipped = 0
        for raw in document.modelspace():
            handle = getattr(raw.dxf, "handle", None)
            try:
                entity = self._convert(raw)
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
            },
        )

    def _convert(self, raw) -> DrawingEntity | None:
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
            attributes["name"] = str(raw.dxf.name)
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
