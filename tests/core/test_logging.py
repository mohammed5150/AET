"""Tests for structured and audit logging (SDS-002 §11)."""

import json
import logging
from pathlib import Path

import pytest

from aet.core.config import AppConfig
from aet.core.errors import InfrastructureError
from aet.core.logging import (
    AUDIT_LOG_FILE,
    AUDIT_LOGGER_NAME,
    DIAGNOSTIC_LOG_FILE,
    DIAGNOSTIC_LOGGER_NAME,
    TRACE,
    configure_logging,
    get_logger,
    reset_logging,
    resolve_level,
)


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


def test_resolve_level_rejects_unknown_names():
    assert resolve_level("info") == logging.INFO
    assert resolve_level("TRACE") == TRACE
    with pytest.raises(InfrastructureError):
        resolve_level("CHATTY")


def _events(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def test_unconfigured_logging_discards_lifecycle_events(tmp_path: Path):
    # Regression guard: without sinks, the standard library drops everything
    # below WARNING, so INFO and audit events are emitted but never stored.
    reset_logging()
    logger = get_logger("test-component")
    logger.info("normal lifecycle event")
    logger.audit("significant action")
    assert not (tmp_path / DIAGNOSTIC_LOG_FILE).exists()


def test_configure_logging_persists_diagnostic_and_audit_events(tmp_path: Path):
    configure_logging(AppConfig(log_dir=tmp_path, log_level="INFO"))
    logger = get_logger("test-component")
    logger.info("normal lifecycle event", project_id="proj-1")
    logger.audit("significant action", project_id="proj-1")

    diagnostic = _events(tmp_path / DIAGNOSTIC_LOG_FILE)
    audit = _events(tmp_path / AUDIT_LOG_FILE)
    assert [event["message"] for event in diagnostic] == ["normal lifecycle event"]
    assert [event["message"] for event in audit] == ["significant action"]
    assert diagnostic[0]["project_id"] == "proj-1"
    assert audit[0]["audit"] is True


def test_audit_events_stay_out_of_the_diagnostic_log(tmp_path: Path):
    # SDS-002 §11.5: audit records must not inherit diagnostic verbosity.
    configure_logging(AppConfig(log_dir=tmp_path))
    get_logger("test-component").audit("significant action")
    assert _events(tmp_path / DIAGNOSTIC_LOG_FILE) == []
    assert len(_events(tmp_path / AUDIT_LOG_FILE)) == 1


def test_log_level_filters_diagnostic_events(tmp_path: Path):
    configure_logging(AppConfig(log_dir=tmp_path, log_level="WARNING"))
    logger = get_logger("test-component")
    logger.info("filtered out")
    logger.warn("kept")
    assert [event["message"] for event in _events(tmp_path / DIAGNOSTIC_LOG_FILE)] == [
        "kept"
    ]


def test_repeated_configuration_does_not_duplicate_sinks(tmp_path: Path):
    configure_logging(AppConfig(log_dir=tmp_path))
    configure_logging(AppConfig(log_dir=tmp_path))
    get_logger("test-component").info("written once")
    assert len(_events(tmp_path / DIAGNOSTIC_LOG_FILE)) == 1


def test_configure_logging_leaves_foreign_handlers_alone(tmp_path: Path):
    foreign = logging.Handler()
    logging.getLogger(DIAGNOSTIC_LOGGER_NAME).addHandler(foreign)
    try:
        configure_logging(AppConfig(log_dir=tmp_path))
        assert foreign in logging.getLogger(DIAGNOSTIC_LOGGER_NAME).handlers
    finally:
        logging.getLogger(DIAGNOSTIC_LOGGER_NAME).removeHandler(foreign)


def test_unwritable_log_dir_is_an_infrastructure_error(tmp_path: Path):
    blocker = tmp_path / "logs"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(InfrastructureError) as raised:
        configure_logging(AppConfig(log_dir=blocker))
    assert raised.value.code == "INFRASTRUCTURE_ERROR"
    assert raised.value.remediation


def test_reset_logging_restores_the_unconfigured_state(tmp_path: Path):
    configure_logging(AppConfig(log_dir=tmp_path))
    reset_logging()
    diagnostic = logging.getLogger(DIAGNOSTIC_LOGGER_NAME)
    audit = logging.getLogger(AUDIT_LOGGER_NAME)
    assert diagnostic.handlers == []
    assert audit.handlers == []
    assert audit.propagate is True
    assert diagnostic.level == logging.NOTSET
