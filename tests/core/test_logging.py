"""Tests for structured and audit logging (SDS-002 §11)."""

import json
import logging

from app.core.logging import TRACE, get_logger


def test_structured_event_carries_context_fields(caplog):
    logger = get_logger("test-component")
    with caplog.at_level(logging.INFO, logger="aet"):
        logger.info(
            "Stage completed",
            correlation_id="cid-1",
            project_id="proj-1",
            stage="ingestion",
            operation="register-input",
        )
    event = json.loads(caplog.records[-1].message)
    assert event["message"] == "Stage completed"
    assert event["component"] == "test-component"
    assert event["correlation_id"] == "cid-1"
    assert event["project_id"] == "proj-1"
    assert event["stage"] == "ingestion"
    assert event["operation"] == "register-input"
    assert event["severity"] == "INFO"
    assert event["audit"] is False
    assert event["timestamp"]


def test_audit_events_route_to_audit_logger(caplog):
    logger = get_logger("test-component")
    with caplog.at_level(logging.INFO, logger="aet.audit"):
        logger.audit("Project created", project_id="proj-1")
    record = caplog.records[-1]
    assert record.name == "aet.audit"
    event = json.loads(record.message)
    assert event["audit"] is True


def test_trace_and_fatal_levels_are_registered(caplog):
    logger = get_logger("test-component")
    with caplog.at_level(TRACE, logger="aet"):
        logger.trace("fine-grained event")
        logger.fatal("unrecoverable failure")
    severities = [json.loads(record.message)["severity"] for record in caplog.records]
    assert "TRACE" in severities
    assert "FATAL" in severities
