"""Identifier and timestamp helpers shared across modules."""

import uuid
from datetime import UTC, datetime


def new_id() -> str:
    """Return a stable unique identifier for long-lived entities (SDS-002 §9.5)."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)
