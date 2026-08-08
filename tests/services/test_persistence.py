"""Tests for repository abstractions (SDS-002 §8.9, §9)."""

import logging

from aet.core.logging import AUDIT_LOGGER_NAME, get_logger
from aet.models.project import Project
from aet.services.persistence import (
    RepositoryAuditSink,
    attach_audit_sink,
    detach_audit_sink,
    in_memory_repositories,
)


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


def test_attached_sink_routes_audit_events_into_the_store():
    repos = in_memory_repositories()
    attach_audit_sink(repos)
    get_logger("test-component").audit(
        "Project created", operation="create-project", project_id="p1"
    )
    assert len(repos.audit_events) == 1
    event = repos.audit_events[0]
    assert event["message"] == "Project created"
    assert event["operation"] == "create-project"
    assert event["project_id"] == "p1"
    assert event["audit"] == "True"


def test_diagnostic_events_are_not_recorded_as_audit_events():
    repos = in_memory_repositories()
    attach_audit_sink(repos)
    get_logger("test-component").info("routine diagnostic")
    assert repos.audit_events == []


def test_attaching_twice_replaces_the_previous_sink():
    first = in_memory_repositories()
    second = in_memory_repositories()
    attach_audit_sink(first)
    attach_audit_sink(second)
    get_logger("test-component").audit("Project created")
    assert first.audit_events == []
    assert len(second.audit_events) == 1
    sinks = [
        handler
        for handler in logging.getLogger(AUDIT_LOGGER_NAME).handlers
        if isinstance(handler, RepositoryAuditSink)
    ]
    assert len(sinks) == 1


def test_detached_sink_stops_recording():
    repos = in_memory_repositories()
    attach_audit_sink(repos)
    detach_audit_sink()
    get_logger("test-component").audit("Project created")
    assert repos.audit_events == []


def test_sink_ignores_records_that_are_not_structured_events():
    repos = in_memory_repositories()
    sink = attach_audit_sink(repos)
    for message in ("plain text", "[1, 2, 3]"):
        sink.emit(
            logging.LogRecord(
                name=AUDIT_LOGGER_NAME,
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg=message,
                args=(),
                exc_info=None,
            )
        )
    assert repos.audit_events == []
