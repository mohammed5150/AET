"""Application use cases and workflow orchestration (SDS-002 §8.2).

The :class:`ApplicationService` defines the use cases named in SDS-002 —
create project, import drawings, process drawings, validate project, and
generate report — coordinating engines, persistence, and the plugin runtime
while translating outcomes for the presentation layer.
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import InputError, WorkflowError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.core.plugins import PluginCategory, PluginRuntime
from app.models.project import Project, SourceInput
from app.models.report import Report, ReportArtifact, ReportRequest
from app.modules.asset_engine import AssetEngine
from app.modules.drawing_engine import DrawingEngine
from app.modules.ingestion import IngestionEngine
from app.modules.reporting_engine import (
    MarkdownFormatter,
    ReportFormatter,
    ReportingEngine,
)
from app.modules.validation_engine import (
    ValidationContext,
    ValidationEngine,
    ValidationRule,
    ValidationRunResult,
)
from app.services.persistence import Repositories, in_memory_repositories
from app.services.pipeline import (
    PipelineResult,
    PipelineStage,
    ProcessingPipeline,
)
from app.utils.ids import new_id


class ApplicationService:
    """Coordinates processing steps across modules (SDS-002 §8.2)."""

    def __init__(
        self,
        repositories: Repositories | None = None,
        ingestion: IngestionEngine | None = None,
        drawing: DrawingEngine | None = None,
        assets: AssetEngine | None = None,
        validation: ValidationEngine | None = None,
        reporting: ReportingEngine | None = None,
        plugins: PluginRuntime | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._repos = repositories or in_memory_repositories()
        self._ingestion = ingestion or IngestionEngine()
        self._drawing = drawing or DrawingEngine()
        self._assets = assets or AssetEngine()
        self._validation = validation or ValidationEngine()
        self._reporting = reporting or ReportingEngine()
        self._plugins = plugins or PluginRuntime()
        self._logger = logger or get_logger("application")
        self._pipeline = ProcessingPipeline(self._logger)
        for registered in self._plugins.extensions(PluginCategory.DRAWING_INTERPRETER):
            self._drawing.registry.register_extension(registered.extension)

    # -- use case: create project -----------------------------------------

    def create_project(self, name: str, description: str = "") -> Outcome[Project]:
        correlation_id = new_id()
        if not name.strip():
            error = InputError(
                "Project name must not be empty",
                remediation="Provide a non-empty project name.",
            )
            return Outcome.from_error(error, correlation_id=correlation_id)
        project = Project(name=name.strip(), description=description)
        self._repos.projects.add(project)
        self._logger.audit(
            "Project created",
            operation="create-project",
            project_id=project.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(project, correlation_id=correlation_id)

    # -- use case: import drawings ----------------------------------------

    def import_drawing(self, project_id: str, path: Path) -> Outcome[SourceInput]:
        correlation_id = new_id()
        project = self._repos.projects.get(project_id)
        if project is None:
            return self._unknown_project(project_id, correlation_id)
        outcome = self._ingestion.register_input(
            project, path, correlation_id=correlation_id
        )
        if outcome.success and outcome.payload is not None:
            self._repos.sources.add(outcome.payload)
        return outcome

    # -- use case: process drawings ---------------------------------------

    def process_drawings(self, project_id: str) -> Outcome[PipelineResult]:
        correlation_id = new_id()
        project = self._repos.projects.get(project_id)
        if project is None:
            return self._unknown_project(project_id, correlation_id)
        sources = self._sources_for(project_id)
        if not sources:
            error = WorkflowError(
                f"Project '{project_id}' has no registered source inputs",
                remediation="Import at least one drawing before processing.",
            )
            return Outcome.from_error(error, correlation_id=correlation_id)

        snapshots = []

        def interpret(cid: str) -> Outcome[object]:
            for source in sources:
                outcome = self._drawing.normalize(source, correlation_id=cid)
                if not outcome.success or outcome.payload is None:
                    return outcome
                self._repos.snapshots.add(outcome.payload)
                snapshots.append(outcome.payload)
            return Outcome.ok(
                list(snapshots),
                correlation_id=cid,
                message=f"{len(snapshots)} drawing(s) normalized",
            )

        def derive(cid: str) -> Outcome[object]:
            asset_total = 0
            for snapshot in snapshots:
                outcome = self._assets.derive(snapshot, correlation_id=cid)
                if not outcome.success or outcome.payload is None:
                    return outcome
                for asset in outcome.payload.assets:
                    self._repos.assets.add(asset)
                for relation in outcome.payload.relations:
                    self._repos.relations.add(relation)
                asset_total += len(outcome.payload.assets)
            return Outcome.ok(
                asset_total,
                correlation_id=cid,
                message=f"{asset_total} asset(s) derived",
            )

        result = self._pipeline.execute(
            [
                (PipelineStage.INTERPRETATION, interpret),
                (PipelineStage.ASSET_DERIVATION, derive),
            ],
            correlation_id=correlation_id,
        )
        failure = result.first_failure()
        if failure is not None:
            return Outcome(
                success=False,
                payload=result,
                error_code=failure.error_code,
                message=failure.message,
                correlation_id=correlation_id,
                remediation=failure.remediation,
            )
        return Outcome.ok(result, correlation_id=correlation_id)

    # -- use case: validate project ---------------------------------------

    def validate_project(
        self,
        project_id: str,
        rules: list[ValidationRule] | None = None,
    ) -> Outcome[ValidationRunResult]:
        correlation_id = new_id()
        project = self._repos.projects.get(project_id)
        if project is None:
            return self._unknown_project(project_id, correlation_id)
        all_rules = list(rules or [])
        for registered in self._plugins.extensions(PluginCategory.VALIDATION_RULE):
            all_rules.append(registered.extension)  # type: ignore[arg-type]
        context = ValidationContext(
            project=project,
            snapshots=[
                snapshot
                for snapshot in self._repos.snapshots.list()
                if snapshot.project_id == project_id
            ],
            assets=[
                asset
                for asset in self._repos.assets.list()
                if asset.project_id == project_id
            ],
            relations=self._repos.relations.list(),
        )
        outcome = self._validation.run(
            context, all_rules, correlation_id=correlation_id
        )
        if outcome.success and outcome.payload is not None:
            self._repos.validation_runs.add(outcome.payload.run)
            for result in outcome.payload.results:
                self._repos.validation_results.add(result)
        return outcome

    # -- use case: generate report ----------------------------------------

    def generate_report(
        self,
        project_id: str,
        report_type: str = "project-summary",
        formatters: list[ReportFormatter] | None = None,
    ) -> Outcome[tuple[Report, list[ReportArtifact]]]:
        correlation_id = new_id()
        project = self._repos.projects.get(project_id)
        if project is None:
            return self._unknown_project(project_id, correlation_id)
        all_formatters: list[ReportFormatter] = list(
            formatters or [MarkdownFormatter()]
        )
        for registered in self._plugins.extensions(PluginCategory.REPORT_PROVIDER):
            all_formatters.append(registered.extension)  # type: ignore[arg-type]
        view = self._reporting.compose(
            project=project,
            sources=self._sources_for(project_id),
            snapshots=[
                snapshot
                for snapshot in self._repos.snapshots.list()
                if snapshot.project_id == project_id
            ],
            assets=[
                asset
                for asset in self._repos.assets.list()
                if asset.project_id == project_id
            ],
            results=self._repos.validation_results.list(),
        )
        request = ReportRequest(project_id=project_id, report_type=report_type)
        outcome = self._reporting.generate(
            request, view, all_formatters, correlation_id=correlation_id
        )
        if outcome.success and outcome.payload is not None:
            report, artifacts = outcome.payload
            self._repos.reports.add(report)
            for artifact in artifacts:
                self._repos.report_artifacts.add(artifact)
        return outcome

    # -- helpers -----------------------------------------------------------

    def _sources_for(self, project_id: str) -> list[SourceInput]:
        return [
            source
            for source in self._repos.sources.list()
            if source.project_id == project_id
        ]

    def _unknown_project(self, project_id: str, correlation_id: str) -> Outcome:
        error = WorkflowError(
            f"Unknown project: {project_id}",
            remediation="Create the project before running this operation.",
        )
        self._logger.error(
            str(error),
            project_id=project_id,
            correlation_id=correlation_id,
            error_code=error.code,
        )
        return Outcome.from_error(error, correlation_id=correlation_id)
