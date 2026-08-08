"""Report composition and output formatting (SDS-002 §8.8).

Report composition (building a :class:`ReportView` over project data) is
separated from output formatting (:class:`ReportFormatter` adapters, also the
extension point for report-provider plugins).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from aet.core.errors import ProcessingError
from aet.core.logging import StructuredLogger, get_logger
from aet.core.outcome import Outcome
from aet.models.asset import Asset
from aet.models.drawing import DrawingSnapshot
from aet.models.project import Project, SourceInput
from aet.models.report import Report, ReportArtifact, ReportRequest
from aet.models.validation import ValidationResult

STAGE_NAME = "reporting"


@dataclass(frozen=True, slots=True)
class FindingLine:
    """One validation finding as presented in a report.

    ``reference`` is the rendered citation of the published clause the finding
    was judged against, empty for a rule that checks no published criterion
    (SDS-016 §12.2).
    """

    rule_id: str
    severity: str
    passed: bool
    message: str
    reference: str = ""


@dataclass(frozen=True, slots=True)
class ReportView:
    """Report-ready composition over project, drawing, and asset data."""

    project_id: str
    project_name: str
    source_count: int
    snapshot_count: int
    asset_count: int
    assets_by_type: dict[str, int] = field(default_factory=dict)
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings: list[FindingLine] = field(default_factory=list)


@runtime_checkable
class ReportFormatter(Protocol):
    """Output formatting adapter contract."""

    format_name: str

    def render(self, view: ReportView) -> str:
        """Render the composed view into this formatter's output format."""
        ...


class MarkdownFormatter:
    """Default Markdown output strategy."""

    format_name = "markdown"

    def render(self, view: ReportView) -> str:
        lines = [
            f"# Project Report: {view.project_name}",
            "",
            f"- Project ID: `{view.project_id}`",
            f"- Source inputs: {view.source_count}",
            f"- Drawing snapshots: {view.snapshot_count}",
            f"- Derived assets: {view.asset_count}",
            f"- Validation findings: {len(view.findings)}",
            "",
        ]
        if view.assets_by_type:
            lines.append("## Assets by Type")
            lines.append("")
            for asset_type, count in sorted(view.assets_by_type.items()):
                lines.append(f"- {asset_type}: {count}")
            lines.append("")
        if view.findings_by_severity:
            lines.append("## Findings by Severity")
            lines.append("")
            for severity, count in sorted(view.findings_by_severity.items()):
                lines.append(f"- {severity}: {count}")
            lines.append("")
        if view.findings:
            # The reference column appears only when something cites one, so a
            # report of hygiene findings is not padded with an empty column
            # implying a criterion that was never checked (SDS-016 §12.2).
            cited = any(finding.reference for finding in view.findings)
            lines.append("## Findings")
            lines.append("")
            header = "| Rule | Severity | Status | Message |"
            divider = "| --- | --- | --- | --- |"
            lines.append(f"{header} Reference |" if cited else header)
            lines.append(f"{divider} --- |" if cited else divider)
            for finding in view.findings:
                status = "passed" if finding.passed else "failed"
                row = (
                    f"| {finding.rule_id} | {finding.severity} "
                    f"| {status} | {finding.message} |"
                )
                lines.append(f"{row} {finding.reference} |" if cited else row)
            lines.append("")
        return "\n".join(lines)


class ReportingEngine:
    """Generates report-ready views and renders output artifacts."""

    stage = STAGE_NAME

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger or get_logger("reporting-engine")

    def compose(
        self,
        project: Project,
        sources: list[SourceInput],
        snapshots: list[DrawingSnapshot],
        assets: list[Asset],
        results: list[ValidationResult],
    ) -> ReportView:
        """Compose a report-ready view over project data."""
        severity_counts = Counter(str(result.severity) for result in results)
        return ReportView(
            project_id=project.project_id,
            project_name=project.name,
            source_count=len(sources),
            snapshot_count=len(snapshots),
            asset_count=len(assets),
            assets_by_type=dict(Counter(asset.asset_type for asset in assets)),
            findings_by_severity=dict(severity_counts),
            findings=[
                FindingLine(
                    rule_id=result.rule_id,
                    severity=str(result.severity),
                    passed=result.passed,
                    message=result.message,
                    reference=str(result.citation) if result.citation else "",
                )
                for result in results
            ],
        )

    def generate(
        self,
        request: ReportRequest,
        view: ReportView,
        formatters: list[ReportFormatter],
        *,
        correlation_id: str | None = None,
    ) -> Outcome[tuple[Report, list[ReportArtifact]]]:
        """Render the view through each formatter into report artifacts."""
        report = Report(
            project_id=request.project_id,
            report_type=request.report_type,
            summary=(
                f"{view.asset_count} asset(s), " f"{len(view.findings)} finding(s)"
            ),
        )
        artifacts: list[ReportArtifact] = []
        for formatter in formatters:
            try:
                content = formatter.render(view)
            except Exception as exc:  # noqa: BLE001 - wrap adapter failures
                message = (
                    f"Report formatter '{formatter.format_name}' " f"failed: {exc}"
                )
                self._logger.error(
                    message,
                    stage=self.stage,
                    project_id=request.project_id,
                    correlation_id=correlation_id,
                    error_code=ProcessingError.code,
                )
                return Outcome.fail(
                    ProcessingError.code,
                    message,
                    correlation_id=correlation_id,
                )
            artifacts.append(
                ReportArtifact(
                    report_id=report.report_id,
                    format_name=formatter.format_name,
                    content=content,
                )
            )
        self._logger.audit(
            f"Report generated with {len(artifacts)} artifact(s)",
            stage=self.stage,
            operation="generate-report",
            project_id=request.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok((report, artifacts), correlation_id=correlation_id)
