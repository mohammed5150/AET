"""Tests for the ingestion engine (SDS-002 §8.4)."""

import hashlib
from pathlib import Path

from app.models.project import Project
from app.modules.ingestion import IngestionEngine


def test_register_input_produces_hashed_source(tmp_path: Path):
    drawing = tmp_path / "apron.dwg"
    drawing.write_bytes(b"fake dwg content")
    project = Project(name="Test")
    outcome = IngestionEngine().register_input(project, drawing, correlation_id="cid-1")
    assert outcome.success
    source = outcome.payload
    assert source is not None
    assert source.project_id == project.project_id
    assert source.file_hash == hashlib.sha256(b"fake dwg content").hexdigest()
    assert source.provenance == f"filesystem:{drawing}"
    assert source.file_format == "dwg"
    assert outcome.correlation_id == "cid-1"


def test_missing_file_returns_input_error_outcome(tmp_path: Path):
    project = Project(name="Test")
    outcome = IngestionEngine().register_input(
        project, tmp_path / "missing.dwg", correlation_id="cid-2"
    )
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"
    assert outcome.remediation
    assert outcome.correlation_id == "cid-2"
