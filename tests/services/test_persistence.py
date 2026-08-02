"""Tests for repository abstractions (SDS-002 §8.9, §9)."""

from app.models.project import Project
from app.services.persistence import in_memory_repositories


def test_repositories_round_trip_entities():
    repos = in_memory_repositories()
    project = Project(name="Test")
    repos.projects.add(project)
    assert repos.projects.get(project.project_id) is project
    assert repos.projects.list() == [project]
    assert repos.projects.get("unknown") is None


def test_audit_events_are_appended_immutably():
    repos = in_memory_repositories()
    event = {"operation": "create-project", "project_id": "p1"}
    repos.record_audit_event(event)
    event["operation"] = "mutated"
    assert repos.audit_events == [{"operation": "create-project", "project_id": "p1"}]
