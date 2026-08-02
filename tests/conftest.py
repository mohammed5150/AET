"""Shared fixtures for the AET test suite."""

from pathlib import Path

import ezdxf
import pytest


@pytest.fixture
def dxf_file(tmp_path: Path) -> Path:
    """A minimal valid DXF file containing one line entity."""
    path = tmp_path / "drawing.dxf"
    document = ezdxf.new("R2010")
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(path)
    return path
