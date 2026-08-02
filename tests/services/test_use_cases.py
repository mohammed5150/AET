"""Tests for application use cases (SDS-002 §8.2, §12.2)."""

from pathlib import Path

from app.services.use_cases import ApplicationService


def _project_with_drawing(dxf_file: Path) -> tuple[ApplicationService, str]:
    service = ApplicationService()
    project = service.create_project("Taxiway Kilo").payload
    assert project is not None
    assert service.import_drawing(project.project_id, dxf_file).success
    return service, project.project_id


def test_create_project_rejects_empty_name():
    outcome = ApplicationService().create_project("   ")
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"


def test_operations_on_unknown_project_are_workflow_errors(tmp_path: Path):
    service = ApplicationService()
    drawing = tmp_path / "kilo.dwg"
    drawing.write_bytes(b"content")
    for outcome in (
        service.import_drawing("nope", drawing),
        service.process_drawings("nope"),
        service.validate_project("nope"),
        service.generate_report("nope"),
    ):
        assert not outcome.success
        assert outcome.error_code == "WORKFLOW_ERROR"


def test_process_requires_imported_drawings():
    service = ApplicationService()
    project = service.create_project("Empty").payload
    assert project is not None
    outcome = service.process_drawings(project.project_id)
    assert not outcome.success
    assert outcome.error_code == "WORKFLOW_ERROR"
    assert outcome.remediation


def test_full_workflow_happy_path(dxf_file: Path):
    service, project_id = _project_with_drawing(dxf_file)

    processed = service.process_drawings(project_id)
    assert processed.success
    assert processed.payload is not None
    assert processed.payload.succeeded

    validated = service.validate_project(project_id)
    assert validated.success
    assert validated.payload is not None

    reported = service.generate_report(project_id)
    assert reported.success
    assert reported.payload is not None
    report, artifacts = reported.payload
    assert report.report_type == "project-summary"
    assert artifacts and artifacts[0].format_name == "markdown"
    assert "Taxiway Kilo" in artifacts[0].content
