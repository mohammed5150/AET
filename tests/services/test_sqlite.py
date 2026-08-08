"""Tests for SDS-013: SQLite persistence."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from aet.core.errors import InfrastructureError
from aet.models.asset import Asset, AssetRelation
from aet.models.drawing import DrawingEntity, DrawingLayer, DrawingSnapshot
from aet.models.geometry import Coordinate
from aet.models.project import Project, SourceInput
from aet.models.report import Report, ReportArtifact
from aet.models.validation import RunStatus, Severity, ValidationResult, ValidationRun
from aet.services.persistence import Repositories, in_memory_repositories
from aet.services.serialization import from_document, to_document
from aet.services.sqlite import (
    SqliteRepository,
    all_tables,
    connect,
    sqlite_repositories,
)


def _asset() -> Asset:
    return Asset(
        project_id="p1",
        snapshot_id="snap-1",
        asset_type="light-fitting",
        name="TCC102-01/067",
        location=Coordinate(easting=261800.5, northing=2703500.25, zone="40 N"),
        attributes={"circuit": "TCC102", "circuit_family": "TCC"},
        source_entity_ids=["e1", "e2"],
    )


def _snapshot() -> DrawingSnapshot:
    return DrawingSnapshot(
        project_id="p1",
        source_input_id="in-1",
        layers=[DrawingLayer(name="AGL-TCL", entity_count=2)],
        entities=[
            DrawingEntity(
                entity_type="insert",
                layer="AGL-TCL",
                attributes={"name": "TCL_LIGHT", "attr.TAG": "TCC102-01/067"},
                geometry={"position": [261800.0, 2703500.0], "rotation": 45.0},
                geometry_ref="2F",
            )
        ],
        metadata={"units": "6", "entity_count": "1"},
    )


# -- §9.1 every model round-trips ------------------------------------------


@pytest.mark.parametrize(
    "instance",
    [
        Project(name="Taxiway Kilo", configuration={"k": "v"}),
        SourceInput(project_id="p1", path="/d.dxf", file_hash="h", file_format="dxf"),
        _snapshot(),
        _asset(),
        Asset(project_id="p1", snapshot_id="", asset_type="agl-pit", name="HH.1"),
        AssetRelation(relation_type="feeds", from_asset_id="a", to_asset_id="b"),
        ValidationRun(project_id="p1", rule_ids=["r1", "r2"]),
        ValidationResult(
            rule_id="agl.spacing",
            severity=Severity.WARNING,
            passed=False,
            message="m",
            evidence={"count": "3"},
        ),
        Report(project_id="p1", report_type="project-summary", version=2),
        ReportArtifact(report_id="r1", format_name="markdown", content="# Title"),
    ],
)
def test_every_model_round_trips_unchanged(instance):
    restored = from_document(type(instance), to_document(instance))
    assert restored == instance


def test_nested_and_optional_types_survive_the_round_trip():
    restored = from_document(Asset, to_document(_asset()))
    assert isinstance(restored.location, Coordinate)
    assert restored.location.zone == "40 N"
    assert isinstance(restored.created_at, datetime)
    assert restored.source_entity_ids == ["e1", "e2"]

    snapshot = from_document(DrawingSnapshot, to_document(_snapshot()))
    assert isinstance(snapshot.layers[0], DrawingLayer)
    assert isinstance(snapshot.entities[0], DrawingEntity)
    # Untyped geometry payloads pass through as written.
    assert snapshot.entities[0].geometry == {
        "position": [261800.0, 2703500.0],
        "rotation": 45.0,
    }


def test_enums_are_restored_as_enums_not_strings():
    run = from_document(ValidationRun, to_document(ValidationRun(project_id="p1")))
    assert run.status is RunStatus.RUNNING
    result = from_document(
        ValidationResult,
        to_document(
            ValidationResult(
                rule_id="r", severity=Severity.ERROR, passed=False, message="m"
            )
        ),
    )
    assert result.severity is Severity.ERROR


def test_an_asset_without_a_location_round_trips_as_none():
    asset = Asset(project_id="p1", snapshot_id="", asset_type="sign", name="S.1")
    assert from_document(Asset, to_document(asset)).location is None


# -- §9.2 a missing field keeps its default --------------------------------


def test_a_document_missing_a_field_falls_back_to_its_default():
    # A model that gains a field must still read rows written before it.
    document = to_document(_asset())
    del document["source_entity_ids"]
    del document["attributes"]
    restored = from_document(Asset, document)
    assert restored.source_entity_ids == []
    assert restored.attributes == {}
    assert restored.name == "TCC102-01/067"


def test_a_non_mapping_document_is_rejected():
    with pytest.raises(TypeError):
        from_document(Asset, ["not", "a", "mapping"])


# -- §9.3 both stores build the same bundle --------------------------------


def test_both_stores_produce_the_same_bundle_type(tmp_path: Path):
    memory = in_memory_repositories()
    disk = sqlite_repositories(connect(tmp_path / "aet.db"))
    assert isinstance(memory, Repositories)
    assert isinstance(disk, Repositories)


# -- §9.4 repository semantics match the in-memory store -------------------


@pytest.fixture
def repositories(tmp_path: Path) -> Repositories:
    return sqlite_repositories(connect(tmp_path / "aet.db"))


def test_add_get_and_list_behave_like_the_in_memory_store(repositories):
    project = Project(name="Taxiway Kilo")
    repositories.projects.add(project)
    assert repositories.projects.get(project.project_id) == project
    assert repositories.projects.list() == [project]
    assert repositories.projects.get("unknown") is None


def test_re_adding_the_same_identifier_replaces_the_entity(repositories):
    project = Project(name="First")
    repositories.projects.add(project)
    project.name = "Renamed"
    repositories.projects.add(project)
    assert [p.name for p in repositories.projects.list()] == ["Renamed"]


def test_tables_exist_for_every_data_domain(tmp_path: Path):
    connection = connect(tmp_path / "aet.db")
    sqlite_repositories(connection)
    tables = set(all_tables(connection))
    assert {
        "projects",
        "source_inputs",
        "drawing_snapshots",
        "assets",
        "asset_relations",
        "validation_runs",
        "validation_results",
        "reports",
        "report_artifacts",
        "audit_events",
    } <= tables


# -- §9.5 state survives the process -------------------------------------


def test_entities_written_by_one_connection_are_read_by_another(tmp_path: Path):
    database = tmp_path / "aet.db"
    written = _asset()
    sqlite_repositories(connect(database)).assets.add(written)

    # A separate connection stands in for a separate process.
    reopened = sqlite_repositories(connect(database))
    [restored] = reopened.assets.list()
    assert restored == written
    assert restored.location == written.location


def test_a_full_snapshot_survives_with_its_entities(tmp_path: Path):
    database = tmp_path / "aet.db"
    sqlite_repositories(connect(database)).snapshots.add(_snapshot())
    [restored] = sqlite_repositories(connect(database)).snapshots.list()
    assert restored.entities[0].attributes["attr.TAG"] == "TCC102-01/067"
    assert restored.layers[0].entity_count == 2


# -- §9.6 scoped reads ------------------------------------------------------


def test_scoped_reads_return_only_that_projects_entities(repositories):
    kilo = Asset(project_id="kilo", snapshot_id="s", asset_type="sign", name="K.1")
    lima = Asset(project_id="lima", snapshot_id="s", asset_type="sign", name="L.1")
    repositories.assets.add(kilo)
    repositories.assets.add(lima)
    assert [a.name for a in repositories.assets.list_for_project("kilo")] == ["K.1"]
    assert [a.name for a in repositories.assets.list_for_project("lima")] == ["L.1"]
    assert repositories.assets.list_for_project("absent") == []


def test_scoped_reads_work_for_tables_without_a_scope_column(repositories):
    # A relation carries no project of its own, so its scoped read filters.
    relation = AssetRelation(relation_type="feeds", from_asset_id="a", to_asset_id="b")
    repositories.relations.add(relation)
    assert repositories.relations.list_for_project("anything") == []


# -- §9.7 the audit trail persists -----------------------------------------


def test_audit_events_persist_and_keep_their_order(tmp_path: Path):
    database = tmp_path / "aet.db"
    first = sqlite_repositories(connect(database))
    first.record_audit_event({"operation": "create-project", "project_id": "p1"})
    first.record_audit_event({"operation": "generate-report", "project_id": "p1"})

    reopened = sqlite_repositories(connect(database))
    assert [event["operation"] for event in reopened.audit_events] == [
        "create-project",
        "generate-report",
    ]


def test_the_in_memory_audit_trail_still_copies_defensively():
    repositories = in_memory_repositories()
    event = {"operation": "create-project"}
    repositories.record_audit_event(event)
    event["operation"] = "mutated"
    assert repositories.audit_events == [{"operation": "create-project"}]


# -- §9.8 database failures are infrastructure errors -----------------------


def test_opening_an_unusable_path_is_an_infrastructure_error(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(InfrastructureError) as raised:
        connect(blocker / "nested" / "aet.db")
    assert raised.value.code == "INFRASTRUCTURE_ERROR"
    assert raised.value.remediation


def test_a_failing_statement_becomes_an_infrastructure_error(tmp_path: Path):
    connection = connect(tmp_path / "aet.db")
    repository = SqliteRepository(
        connection, "projects", Project, lambda item: item.project_id
    )
    connection.close()  # every later statement now raises sqlite3.ProgrammingError
    with pytest.raises(InfrastructureError) as raised:
        repository.add(Project(name="Taxiway Kilo"))
    assert raised.value.remediation


def test_a_corrupt_document_surfaces_rather_than_returning_a_wrong_entity(
    tmp_path: Path,
):
    connection = connect(tmp_path / "aet.db")
    repositories = sqlite_repositories(connection)
    repositories.projects.add(Project(name="Taxiway Kilo"))
    connection.execute("UPDATE projects SET document = ?", ("{not json",))
    connection.commit()
    # json.JSONDecodeError, so corruption surfaces rather than silently
    # producing a wrong entity.
    with pytest.raises(json.JSONDecodeError):
        repositories.projects.list()


def test_sqlite_errors_are_not_leaked_as_driver_exceptions(tmp_path: Path):
    connection = connect(tmp_path / "aet.db")
    repository = SqliteRepository(
        connection, "projects", Project, lambda item: item.project_id
    )
    connection.close()
    with pytest.raises(InfrastructureError):
        repository.list()
    with pytest.raises(sqlite3.Error):
        connection.execute("SELECT 1")
