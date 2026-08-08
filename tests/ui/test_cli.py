"""Tests for the CLI presentation boundary (SDS-002 §8.1, §12.4)."""

import json
from pathlib import Path

from aet.core.logging import AUDIT_LOG_FILE, DIAGNOSTIC_LOG_FILE
from aet.ui.cli import build_service, main, resolve_config


def test_run_command_writes_report_to_output(dxf_file: Path, capsys, monkeypatch):
    monkeypatch.chdir(dxf_file.parent)
    exit_code = main(["run", "--name", "Apron North", str(dxf_file)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Created project 'Apron North'" in captured.out
    assert "Stage interpretation: succeeded" in captured.out
    assert "Report written: " in captured.out
    written = dxf_file.parent / "output" / "apron-north" / "project-summary-v1.md"
    assert written.is_file()
    assert "# Project Report: Apron North" in written.read_text(encoding="utf-8")


def test_run_command_no_save_prints_report(dxf_file: Path, capsys):
    exit_code = main(["run", "--name", "Apron North", "--no-save", str(dxf_file)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "# Project Report: Apron North" in captured.out
    assert "Report written:" not in captured.out


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


def test_run_writes_diagnostic_and_audit_logs(dxf_file: Path, tmp_path: Path):
    log_dir = tmp_path / "run-logs"
    assert main(["--log-dir", str(log_dir), "run", str(dxf_file)]) == 0

    audit = [
        json.loads(line)
        for line in (log_dir / AUDIT_LOG_FILE).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert (log_dir / DIAGNOSTIC_LOG_FILE).exists()
    operations = {event.get("operation") for event in audit}
    assert "create-project" in operations
    assert "generate-report" in operations
    assert all(event["audit"] is True for event in audit)


def test_run_records_audit_events_in_the_audit_store(dxf_file: Path, capsys):
    service = build_service()
    project = service.create_project("Apron North").payload
    assert project is not None
    assert service.generate_report(project.project_id).success

    operations = {event.get("operation") for event in service.repositories.audit_events}
    assert "create-project" in operations
    assert "generate-report" in operations


def test_log_level_flag_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("AET_LOG_LEVEL", "ERROR")
    args = _parse(["--log-level", "DEBUG", "version"])
    assert resolve_config(args).log_level == "DEBUG"


def test_environment_supplies_defaults_for_unset_flags(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AET_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("AET_DATA_DIR", str(tmp_path / "artifacts"))
    config = resolve_config(_parse(["version"]))
    assert config.log_level == "WARNING"
    assert config.data_dir == tmp_path / "artifacts"


def test_invalid_log_level_is_reported_without_a_traceback(capsys):
    assert main(["--log-level", "CHATTY", "version"]) == 1
    captured = capsys.readouterr()
    assert "error [INFRASTRUCTURE_ERROR]" in captured.err
    assert "hint:" in captured.err
    assert captured.out == ""


def test_unwritable_log_dir_is_reported_without_a_traceback(tmp_path: Path, capsys):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("blocking file", encoding="utf-8")
    assert main(["--log-dir", str(blocker), "version"]) == 1
    assert "error [INFRASTRUCTURE_ERROR]" in capsys.readouterr().err


def _parse(argv: list[str]):
    from aet.ui.cli import build_parser

    return build_parser().parse_args(argv)
