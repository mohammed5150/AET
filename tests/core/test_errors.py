"""Tests for the error taxonomy (SDS-002 §12.2)."""

import pytest

from app.core.errors import (
    AETError,
    InfrastructureError,
    InputError,
    ProcessingError,
    RuleError,
    WorkflowError,
)

EXPECTED = [
    (InputError, "INPUT_ERROR", "input"),
    (ProcessingError, "PROCESSING_ERROR", "processing"),
    (RuleError, "VALIDATION_ERROR", "validation"),
    (InfrastructureError, "INFRASTRUCTURE_ERROR", "infrastructure"),
    (WorkflowError, "WORKFLOW_ERROR", "workflow"),
]


@pytest.mark.parametrize(("error_cls", "code", "category"), EXPECTED)
def test_error_taxonomy_codes_and_categories(error_cls, code, category):
    error = error_cls("boom", remediation="fix it")
    assert isinstance(error, AETError)
    assert error.code == code
    assert error.category == category
    assert error.remediation == "fix it"
    assert str(error) == "boom"
