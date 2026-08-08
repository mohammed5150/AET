"""Project and source-input domain models (SDS-002 §9.2.1, §9.2.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aet.utils.ids import new_id, utc_now


@dataclass(slots=True)
class Project:
    """Project identity, metadata, configuration, and versioning."""

    name: str
    description: str = ""
    configuration: dict[str, str] = field(default_factory=dict)
    version: int = 1
    project_id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)


class SourceRole(StrEnum):
    """What a registered file is for.

    A registry import registers its workbook as a source input just as a
    drawing import does, so without a role the processing pipeline cannot
    tell which files it is meant to interpret (SDS-015 §6).
    """

    DRAWING = "drawing"
    REGISTRY = "registry"


@dataclass(slots=True)
class SourceInput:
    """A registered source file with hash-based provenance."""

    project_id: str
    path: str
    file_hash: str
    role: SourceRole = SourceRole.DRAWING
    file_version: int = 1
    provenance: str = ""
    file_format: str = ""
    input_id: str = field(default_factory=new_id)
    imported_at: datetime = field(default_factory=utc_now)
