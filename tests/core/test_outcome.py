"""Tests for structured outcomes (SDS-002 §12.3)."""

from aet.core.errors import InputError
from aet.core.outcome import Outcome


def test_ok_carries_payload_and_correlation_id():
    outcome = Outcome.ok({"key": "value"}, correlation_id="cid-1")
    assert outcome.success
    assert outcome.payload == {"key": "value"}
    assert outcome.correlation_id == "cid-1"
    assert outcome.error_code is None


def test_fail_carries_code_message_and_remediation():
    outcome: Outcome[str] = Outcome.fail(
        "INPUT_ERROR",
        "File missing",
        correlation_id="cid-2",
        remediation="Check the path",
    )
    assert not outcome.success
    assert outcome.payload is None
    assert outcome.error_code == "INPUT_ERROR"
    assert outcome.message == "File missing"
    assert outcome.remediation == "Check the path"


def test_from_error_maps_expected_errors():
    error = InputError("Corrupt source", remediation="Re-export the DWG")
    outcome: Outcome[str] = Outcome.from_error(error, correlation_id="cid-3")
    assert not outcome.success
    assert outcome.error_code == "INPUT_ERROR"
    assert outcome.message == "Corrupt source"
    assert outcome.remediation == "Re-export the DWG"
    assert outcome.correlation_id == "cid-3"
