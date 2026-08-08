"""Tests for SDS-007 report artifact persistence."""

from pathlib import Path

import pytest

from aet.core.errors import InfrastructureError
from aet.models.project import Project
from aet.models.report import Report, ReportArtifact
from aet.modules.reporting_engine import FileArtifactStore, project_slug


def _artifact(report: Report, content: str = "# Report") -> ReportArtifact:
    return ReportArtifact(
        report_id=report.report_id, format_name="markdown", content=content
    )


def test_slug_is_filesystem_safe():
    assert project_slug(Project(name="AUH Stand 201 / North")) == "auh-stand-201-north"
    fallback = Project(name="!!!")
    assert project_slug(fallback) == fallback.project_id


def test_save_writes_versioned_markdown(tmp_path: Path):
    store = FileArtifactStore(tmp_path)
    project = Project(name="Taxiway Kilo")
    report = Report(project_id=project.project_id, report_type="project-summary")
    location = store.save(project, report, _artifact(report, "# Kilo"))
    written = Path(location)
    assert written == tmp_path / "taxiway-kilo" / "project-summary-v1.md"
    assert written.read_text(encoding="utf-8") == "# Kilo"


def test_save_is_idempotent_per_version(tmp_path: Path):
    store = FileArtifactStore(tmp_path)
    project = Project(name="Kilo")
    report = Report(project_id=project.project_id, report_type="project-summary")
    store.save(project, report, _artifact(report, "first"))
    location = store.save(project, report, _artifact(report, "second"))
    assert Path(location).read_text(encoding="utf-8") == "second"


def test_unknown_format_uses_format_name_extension(tmp_path: Path):
    store = FileArtifactStore(tmp_path)
    project = Project(name="Kilo")
    report = Report(project_id=project.project_id, report_type="summary")
    artifact = ReportArtifact(
        report_id=report.report_id, format_name="csv", content="a,b"
    )
    assert store.save(project, report, artifact).endswith("summary-v1.csv")


def test_storage_failure_raises_infrastructure_error(tmp_path: Path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file, not directory")
    store = FileArtifactStore(blocker)
    project = Project(name="Kilo")
    report = Report(project_id=project.project_id, report_type="summary")
    with pytest.raises(InfrastructureError) as excinfo:
        store.save(project, report, _artifact(report))
    assert excinfo.value.remediation
