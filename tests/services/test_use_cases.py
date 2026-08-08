"""Tests for application use cases (SDS-002 §8.2, §12.2)."""

from pathlib import Path

from app.core.config import AppConfig
from app.models.asset import Asset, AssetRelation
from app.models.geometry import Coordinate
from app.modules.reporting_engine import FileArtifactStore
from app.services.use_cases import ApplicationService


def _service(base_dir: Path) -> ApplicationService:
    return ApplicationService(artifact_store=FileArtifactStore(base_dir / "reports"))


def _project_with_drawing(dxf_file: Path) -> tuple[ApplicationService, str]:
    service = _service(dxf_file.parent)
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


def test_import_asset_registry_persists_assets(tmp_path: Path):
    from openpyxl import Workbook

    registry = tmp_path / "assets.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["name", "assetClass", "mainArea"])
    sheet.append(["TCC1-01/001", "ADB-BI-GG-S-INSET-8IN-2x40W", "ST"])
    sheet.append(["HH.A.001", "AGL PIT", "AUX"])
    workbook.save(registry)

    service = _service(tmp_path)
    project = service.create_project("Registry Demo").payload
    assert project is not None
    outcome = service.import_asset_registry(project.project_id, registry)
    assert outcome.success
    assert outcome.payload is not None
    assert len(outcome.payload.assets) == 2

    reported = service.generate_report(project.project_id)
    assert reported.success and reported.payload is not None
    content = reported.payload[1][0].content
    assert "## Assets by Type" in content
    assert "light-fitting: 1" in content
    assert "agl-pit: 1" in content


def test_import_asset_registry_unknown_project(tmp_path: Path):
    service = ApplicationService()
    outcome = service.import_asset_registry("nope", tmp_path / "assets.xlsx")
    assert not outcome.success
    assert outcome.error_code == "WORKFLOW_ERROR"


def test_validate_default_runs_standard_pack(dxf_file: Path):
    service, project_id = _project_with_drawing(dxf_file)
    assert service.process_drawings(project_id).success

    validated = service.validate_project(project_id)
    assert validated.success and validated.payload is not None
    rule_ids = {result.rule_id for result in validated.payload.results}
    assert "agl.asset.location" in rule_ids
    assert "agl.drawing.empty-layers" in rule_ids
    assert len(validated.payload.results) == 5

    opted_out = service.validate_project(project_id, rules=[])
    assert opted_out.success and opted_out.payload is not None
    assert opted_out.payload.results == []


def _asset(service: ApplicationService, project_id: str, name: str) -> Asset:
    asset = Asset(
        project_id=project_id,
        snapshot_id="",
        asset_type="light-fitting",
        name=name,
        location=Coordinate(easting=1.0, northing=2.0, zone="40 N"),
    )
    service.repositories.assets.add(asset)
    return asset


def _two_projects() -> tuple[ApplicationService, str, str]:
    service = ApplicationService()
    first = service.create_project("Taxiway Kilo").payload
    second = service.create_project("Taxiway Lima").payload
    assert first is not None and second is not None
    return service, first.project_id, second.project_id


def test_validation_context_excludes_another_projects_relations():
    # Relations carry no project of their own; an unscoped read would put
    # Lima's relations into Kilo's validation context.
    service, kilo, lima = _two_projects()
    lima_relation = AssetRelation(
        relation_type="feeds",
        from_asset_id=_asset(service, lima, "LIC1-01/001").asset_id,
        to_asset_id=_asset(service, lima, "LIC1-01/002").asset_id,
    )
    service.repositories.relations.add(lima_relation)
    kilo_relation = AssetRelation(
        relation_type="feeds",
        from_asset_id=_asset(service, kilo, "TCC1-01/001").asset_id,
        to_asset_id=_asset(service, kilo, "TCC1-01/002").asset_id,
    )
    service.repositories.relations.add(kilo_relation)

    captured = []

    class _RelationSpy:
        rule_id = "spy.relations"
        description = "Captures the relations a rule can see"

        def evaluate(self, context):
            captured.append(list(context.relations))
            return []

    assert service.validate_project(kilo, rules=[_RelationSpy()]).success
    assert captured == [[kilo_relation]]


def test_validation_context_excludes_relations_spanning_projects():
    service, kilo, lima = _two_projects()
    service.repositories.relations.add(
        AssetRelation(
            relation_type="feeds",
            from_asset_id=_asset(service, kilo, "TCC1-01/001").asset_id,
            to_asset_id=_asset(service, lima, "LIC1-01/001").asset_id,
        )
    )

    captured = []

    class _RelationSpy:
        rule_id = "spy.relations"
        description = "Captures the relations a rule can see"

        def evaluate(self, context):
            captured.append(list(context.relations))
            return []

    assert service.validate_project(kilo, rules=[_RelationSpy()]).success
    assert captured == [[]]


def test_report_excludes_another_projects_findings():
    # Findings reference their run, not their project; an unscoped read would
    # print Lima's findings in Kilo's report.
    service, kilo, lima = _two_projects()
    _asset(service, lima, "LIC1-01/001")
    _asset(service, lima, "LIC1-01/001")  # duplicate name -> ERROR finding
    assert service.validate_project(lima).success
    assert service.validate_project(kilo).success

    reported = service.generate_report(kilo)
    assert reported.success and reported.payload is not None
    content = reported.payload[1][0].content
    assert "Duplicate asset names found" not in content
    assert "All asset names unique" in content
    assert "LIC1-01/001" not in content

    lima_report = service.generate_report(lima)
    assert lima_report.success and lima_report.payload is not None
    assert "Duplicate asset names found" in lima_report.payload[1][0].content


def test_report_counts_only_the_projects_own_assets():
    service, kilo, lima = _two_projects()
    _asset(service, kilo, "TCC1-01/001")
    _asset(service, lima, "LIC1-01/001")
    _asset(service, lima, "LIC1-01/002")

    reported = service.generate_report(kilo)
    assert reported.success and reported.payload is not None
    assert "light-fitting: 1" in reported.payload[1][0].content


def test_service_exposes_the_configuration_it_was_wired_with():
    config = AppConfig(log_level="DEBUG", data_dir=Path("/srv/artifacts"))
    service = ApplicationService(config=config)
    assert service.config is config
    assert service.config.data_dir == Path("/srv/artifacts")


def test_service_defaults_to_a_usable_configuration():
    assert ApplicationService().config == AppConfig()


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
    written = Path(artifacts[0].location)
    assert written.is_file()
    assert written.name == "project-summary-v1.md"
    assert "Taxiway Kilo" in written.read_text(encoding="utf-8")


def test_report_versions_increment(dxf_file: Path):
    service, project_id = _project_with_drawing(dxf_file)
    first = service.generate_report(project_id)
    second = service.generate_report(project_id)
    assert first.payload is not None and second.payload is not None
    assert first.payload[0].version == 1
    assert second.payload[0].version == 2
    assert Path(first.payload[1][0].location).is_file()
    assert Path(second.payload[1][0].location).is_file()
    assert first.payload[1][0].location != second.payload[1][0].location


def test_generate_report_without_saving(dxf_file: Path):
    service, project_id = _project_with_drawing(dxf_file)
    reported = service.generate_report(project_id, save=False)
    assert reported.success and reported.payload is not None
    assert reported.payload[1][0].location == ""
    assert not (dxf_file.parent / "reports").exists()


def test_storage_failure_is_infrastructure_error(dxf_file: Path):
    from app.core.errors import InfrastructureError

    class BrokenStore:
        def save(self, project, report, artifact) -> str:
            raise InfrastructureError("disk full")

    service = ApplicationService(artifact_store=BrokenStore())
    project = service.create_project("Broken Store").payload
    assert project is not None
    outcome = service.generate_report(project.project_id)
    assert not outcome.success
    assert outcome.error_code == "INFRASTRUCTURE_ERROR"
    assert service._repos.reports.list() == []
