"""Report artifact persistence (SDS-007).

Rendered artifacts are written to file storage per the SDS-002 §9.4
storage split; the repositories keep the metadata, the filesystem keeps
the exported documents.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from aet.core.config import AppConfig
from aet.core.errors import InfrastructureError
from aet.models.project import Project
from aet.models.report import Report, ReportArtifact

_FORMAT_EXTENSIONS = {"markdown": "md"}


def project_slug(project: Project) -> str:
    """Filesystem-safe slug for a project (SDS-007 §3.1)."""
    slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-")
    return slug or project.project_id


class ArtifactStore(Protocol):
    """Artifact persistence contract (SDS-007 §3)."""

    def save(self, project: Project, report: Report, artifact: ReportArtifact) -> str:
        """Persist one rendered artifact and return its location."""
        ...


class FileArtifactStore:
    """Writes artifacts below a base directory (SDS-007 §3.1)."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir if base_dir is not None else AppConfig().data_dir

    def save(self, project: Project, report: Report, artifact: ReportArtifact) -> str:
        extension = _FORMAT_EXTENSIONS.get(artifact.format_name, artifact.format_name)
        target = (
            Path(self._base_dir)
            / project_slug(project)
            / f"{report.report_type}-v{report.version}.{extension}"
        )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(artifact.content, encoding="utf-8")
        except OSError as exc:
            raise InfrastructureError(
                f"Failed to write report artifact to {target}: {exc}",
                remediation=(
                    "Check that the output directory is writable and has " "free space."
                ),
            ) from exc
        return str(target)
