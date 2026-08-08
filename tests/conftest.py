"""Shared fixtures for the AET test suite."""

from pathlib import Path

import ezdxf
import pytest

from app.core.logging import reset_logging
from app.services.persistence import detach_audit_sink


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path_factory, monkeypatch):
    """Keep log sinks out of the repository and reset global logging state.

    ``configure_logging`` and ``attach_audit_sink`` mutate process-wide
    loggers, so without this a test that configures logging would write into
    the repository's own ``logs/`` and leak handlers into later tests.
    """
    monkeypatch.setenv("AET_LOG_DIR", str(tmp_path_factory.mktemp("logs")))
    yield
    detach_audit_sink()
    reset_logging()


@pytest.fixture
def dxf_file(tmp_path: Path) -> Path:
    """A minimal valid DXF file containing one line entity."""
    path = tmp_path / "drawing.dxf"
    document = ezdxf.new("R2010")
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(path)
    return path
