"""Tests for SDS-003: DXF interpretation and format-aware selection."""

from pathlib import Path

import ezdxf

from app.models.drawing import DrawingSnapshot
from app.models.project import SourceInput
from app.modules.drawing_engine import (
    DrawingEngine,
    DxfInterpreter,
    InterpreterRegistry,
)


def _source_for(path: Path) -> SourceInput:
    return SourceInput(
        project_id="p1",
        path=str(path),
        file_hash="h",
        file_format=path.suffix.lower().lstrip("."),
    )


def _rich_dxf(path: Path) -> None:
    document = ezdxf.new("R2010", setup=False)
    document.header["$INSUNITS"] = 6
    document.layers.add("AGL-EDGE")
    document.layers.add("AGL-CL")
    document.layers.add("EMPTY")
    document.blocks.new(name="EDGE_LIGHT")
    msp = document.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "AGL-EDGE"})
    msp.add_lwpolyline(
        [(0, 0), (5, 5), (10, 0)], close=True, dxfattribs={"layer": "AGL-CL"}
    )
    msp.add_circle((1, 1), radius=0.3, dxfattribs={"layer": "AGL-EDGE"})
    msp.add_arc(
        (2, 2),
        radius=1.0,
        start_angle=0,
        end_angle=90,
        dxfattribs={"layer": "AGL-CL"},
    )
    msp.add_blockref(
        "EDGE_LIGHT", (3, 4), dxfattribs={"layer": "AGL-EDGE", "rotation": 45.0}
    )
    text = msp.add_text("EL-01", dxfattribs={"layer": "AGL-EDGE"})
    text.set_placement((3, 4.5))
    msp.add_point((7, 8), dxfattribs={"layer": "AGL-CL"})
    msp.add_spline(
        [(0, 0), (1, 2), (3, 1)], dxfattribs={"layer": "AGL-CL"}
    )  # unsupported type -> skipped, not fatal
    document.saveas(path)


def test_dxf_interpretation_normalizes_entities(tmp_path: Path):
    path = tmp_path / "apron.dxf"
    _rich_dxf(path)
    outcome = DrawingEngine().normalize(_source_for(path), correlation_id="c1")
    assert outcome.success
    snapshot = outcome.payload
    assert isinstance(snapshot, DrawingSnapshot)

    by_type = {entity.entity_type: entity for entity in snapshot.entities}
    assert set(by_type) == {
        "line",
        "lwpolyline",
        "circle",
        "arc",
        "insert",
        "text",
        "point",
    }
    assert by_type["line"].geometry == {"points": [[0.0, 0.0], [10.0, 0.0]]}
    assert by_type["lwpolyline"].geometry["closed"] is True
    assert len(by_type["lwpolyline"].geometry["points"]) == 3
    assert by_type["circle"].geometry == {"center": [1.0, 1.0], "radius": 0.3}
    assert by_type["arc"].geometry["start_angle"] == 0.0
    assert by_type["arc"].geometry["end_angle"] == 90.0
    assert by_type["insert"].attributes["name"] == "EDGE_LIGHT"
    assert by_type["insert"].geometry["rotation"] == 45.0
    assert by_type["text"].attributes["content"] == "EL-01"
    assert by_type["text"].geometry["position"] == [3.0, 4.5]
    assert by_type["point"].geometry["position"] == [7.0, 8.0]
    assert all(entity.geometry_ref for entity in snapshot.entities)

    layer_counts = {layer.name: layer.entity_count for layer in snapshot.layers}
    assert layer_counts["AGL-EDGE"] == 4
    assert layer_counts["AGL-CL"] == 3
    assert layer_counts["EMPTY"] == 0

    assert snapshot.metadata["units"] == "6"
    assert snapshot.metadata["entity_count"] == "7"
    assert snapshot.metadata["skipped_entities"] == "1"
    assert snapshot.metadata["dxf_version"] == "AC1024"
    assert snapshot.metadata["source_path"] == str(path)


def test_corrupt_dxf_fails_with_input_error(tmp_path: Path):
    path = tmp_path / "broken.dxf"
    path.write_text("this is not a dxf file")
    outcome = DrawingEngine().normalize(_source_for(path), correlation_id="c2")
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"
    assert outcome.remediation


def test_dwg_without_backend_fails_with_conversion_hint(tmp_path: Path):
    from app.modules.drawing_engine import (
        DwgConversionInterpreter,
        InterpreterRegistry,
    )

    path = tmp_path / "apron.dwg"
    path.write_bytes(b"binary dwg content")
    registry = InterpreterRegistry()
    registry.register("dxf", DxfInterpreter())
    registry.register("dwg", DwgConversionInterpreter(converters=[]))
    engine = DrawingEngine(registry=registry)
    outcome = engine.normalize(_source_for(path), correlation_id="c3")
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"
    assert "convert the file to DXF manually" in (outcome.remediation or "")


def test_unknown_format_lists_supported_formats(tmp_path: Path):
    path = tmp_path / "model.xyz"
    path.write_text("data")
    outcome = DrawingEngine().normalize(_source_for(path))
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"
    assert "dxf" in (outcome.remediation or "")


def test_registry_selects_extension_by_declared_format(dxf_file: Path):
    class CustomInterpreter:
        supported_formats = ("fmtx",)

        def interpret(self, source):
            return DrawingSnapshot(
                project_id=source.project_id,
                source_input_id=source.input_id,
                metadata={"interpreter": "custom"},
            )

    registry = InterpreterRegistry()
    registry.register("dxf", DxfInterpreter())
    assert registry.register_extension(CustomInterpreter()) == ["fmtx"]
    assert registry.formats() == ["dxf", "fmtx"]

    engine = DrawingEngine(registry=registry)
    source = SourceInput(
        project_id="p1", path="/data/model.fmtx", file_hash="h", file_format="fmtx"
    )
    outcome = engine.normalize(source)
    assert outcome.success
    assert outcome.payload.metadata["interpreter"] == "custom"
