"""Report domain models (SDS-002 §8.8, §9.2.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.utils.ids import new_id, utc_now


@dataclass(slots=True)
class ReportRequest:
    """A user or system request to generate a report."""

    project_id: str
    report_type: str
    parameters: dict[str, str] = field(default_factory=dict)
    request_id: str = field(default_factory=new_id)


@dataclass(slots=True)
class Report:
    """Metadata for one generated report, with version history support."""

    project_id: str
    report_type: str
    summary: str = ""
    version: int = 1
    report_id: str = field(default_factory=new_id)
    generated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ReportArtifact:
    """One rendered output of a report in a specific format."""

    report_id: str
    format_name: str
    content: str
    location: str = ""
    artifact_id: str = field(default_factory=new_id)
