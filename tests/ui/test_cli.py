"""Tests for the CLI presentation boundary (SDS-002 §8.1, §12.4)."""

from pathlib import Path

from app.ui.cli import main


def test_run_command_executes_full_pipeline(dxf_file: Path, capsys):
    exit_code = main(["run", "--name", "Apron North", str(dxf_file)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Created project 'Apron North'" in captured.out
    assert "Stage interpretation: succeeded" in captured.out
    assert "# Project Report: Apron North" in captured.out


def test_run_command_fails_cleanly_on_unconvertible_dwg(tmp_path: Path, capsys):
    # Garbage DWG bytes: fails as INPUT_ERROR (no converter backend) or
    # PROCESSING_ERROR (backend rejects the corrupt file) per environment.
    drawing = tmp_path / "apron.dwg"
    drawing.write_bytes(b"binary dwg content")
    exit_code = main(["run", "--name", "Apron North", str(drawing)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error [" in captured.err


def test_run_command_translates_failures_for_users(tmp_path: Path, capsys):
    exit_code = main(["run", str(tmp_path / "missing.dwg")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error [INPUT_ERROR]" in captured.err
    assert "hint:" in captured.err


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.startswith("aet ")
