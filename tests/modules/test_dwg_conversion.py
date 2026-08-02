"""Tests for SDS-006: DWG conversion adapter and interpreter."""

import shutil
from pathlib import Path

import ezdxf
import pytest

from app.core.errors import InputError, ProcessingError
from app.models.project import SourceInput
from app.modules.drawing_engine import (
    DrawingEngine,
    DwgConversionInterpreter,
    InterpreterRegistry,
    LibreDwgConverter,
    default_registry,
)


class FakeConverter:
    """Produces a small real DXF, standing in for an external tool."""

    name = "fake"

    def __init__(self, available: bool = True):
        self._available = available
        self.calls = 0

    def available(self) -> bool:
        return self._available

    def convert(self, dwg_path: Path, output_dir: Path) -> Path:
        self.calls += 1
        produced = output_dir / f"{dwg_path.stem}.dxf"
        document = ezdxf.new("R2010")
        document.layers.add("AGL-EDGE")
        document.modelspace().add_line((0, 0), (5, 0), dxfattribs={"layer": "AGL-EDGE"})
        document.saveas(produced)
        return produced


class ExplodingConverter:
    name = "exploding"

    def available(self) -> bool:
        return True

    def convert(self, dwg_path: Path, output_dir: Path) -> Path:
        raise ProcessingError("converter crashed mid-run")


def _dwg_source(tmp_path: Path) -> SourceInput:
    path = tmp_path / "apron.dwg"
    path.write_bytes(b"pretend dwg bytes")
    return SourceInput(
        project_id="p1",
        path=str(path),
        file_hash="dwg-hash",
        file_format="dwg",
    )


def test_conversion_delegates_and_restores_dwg_provenance(tmp_path: Path):
    source = _dwg_source(tmp_path)
    interpreter = DwgConversionInterpreter(converters=[FakeConverter()])
    snapshot = interpreter.interpret(source)
    assert len(snapshot.entities) == 1
    assert snapshot.entities[0].layer == "AGL-EDGE"
    assert snapshot.metadata["source_path"] == source.path
    assert snapshot.metadata["source_hash"] == "dwg-hash"
    assert snapshot.metadata["converter"] == "fake"
    assert snapshot.metadata["dxf_version"] == "AC1024"


def test_no_backend_fails_with_install_remediation(tmp_path: Path):
    interpreter = DwgConversionInterpreter(converters=[])
    with pytest.raises(InputError) as excinfo:
        interpreter.interpret(_dwg_source(tmp_path))
    assert "convert the file to DXF manually" in (excinfo.value.remediation or "")


def test_backend_chain_skips_unavailable(tmp_path: Path):
    unavailable = FakeConverter(available=False)
    fallback = FakeConverter()
    interpreter = DwgConversionInterpreter(converters=[unavailable, fallback])
    interpreter.interpret(_dwg_source(tmp_path))
    assert unavailable.calls == 0
    assert fallback.calls == 1


def test_converter_failure_becomes_processing_error_outcome(tmp_path: Path):
    registry = InterpreterRegistry()
    registry.register(
        "dwg", DwgConversionInterpreter(converters=[ExplodingConverter()])
    )
    engine = DrawingEngine(registry=registry)
    outcome = engine.normalize(_dwg_source(tmp_path), correlation_id="c1")
    assert not outcome.success
    assert outcome.error_code == "PROCESSING_ERROR"
    assert "converter crashed" in outcome.message


def test_default_registry_covers_dwg():
    assert default_registry().formats() == ["dwg", "dxf"]


@pytest.mark.skipif(
    shutil.which("dxf2dwg") is None or not LibreDwgConverter().available(),
    reason="GNU LibreDWG not installed",
)
def test_real_libredwg_roundtrip(tmp_path: Path, dxf_file: Path):
    import subprocess

    dwg = tmp_path / "roundtrip.dwg"
    subprocess.run(
        ["dxf2dwg", "-o", str(dwg), str(dxf_file)], check=True, capture_output=True
    )
    source = SourceInput(
        project_id="p1", path=str(dwg), file_hash="h", file_format="dwg"
    )
    outcome = DrawingEngine().normalize(source, correlation_id="c-real")
    assert outcome.success
    assert outcome.payload is not None
    assert outcome.payload.metadata["converter"] == "libredwg"
    assert outcome.payload.metadata["source_path"] == str(dwg)
