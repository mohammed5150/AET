"""Application use cases and workflow orchestration (SDS-002 §8.2).

The :class:`ApplicationService` defines the use cases named in SDS-002 —
create project, import drawings, process drawings, validate project, and
generate report — coordinating engines, persistence, and the plugin runtime
while translating outcomes for the presentation layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aet.core.config import AppConfig
from aet.core.errors import InfrastructureError, InputError, WorkflowError
from aet.core.logging import StructuredLogger, get_logger
from aet.core.outcome import Outcome
from aet.core.plugins import PluginCategory, PluginRuntime
from aet.models.asset import Asset, AssetRelation
from aet.models.drawing import DrawingSnapshot
from aet.models.project import Project, SourceInput
from aet.models.report import Report, ReportArtifact, ReportRequest
from aet.models.validation import ValidationResult
from aet.modules.asset_engine import AssetEngine, XlsxAssetRegistryReader
from aet.modules.asset_engine.registry import RegistryImport
from aet.modules.drawing_engine import DrawingEngine
from aet.modules.ingestion import IngestionEngine
from aet.modules.reporting_engine import (
    MarkdownFormatter,
    ReportFormatter,
    ReportingEngine,
)
from aet.modules.validation_engine import (
    ValidationContext,
    ValidationEngine,
    ValidationRule,
    ValidationRunResult,
    standard_rules,
)
from aet.services.persistence import Repositories, in_memory_repositories
from aet.services.pipeline import (
    PipelineResult,
    PipelineStage,
    ProcessingPipeline,
)
from aet.utils.ids import new_id


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
        config: AppConfig | None = None,
    ) -> None:
        self._config = config or AppConfig()
        self._repos = repositories or in_memory_repositories()
        self._ingestion = ingestion or IngestionEngine()
        self._drawing = drawing or DrawingEngine()
        self._assets = assets or AssetEngine()
        self._validation = validation or ValidationEngine()
        self._reporting = reporting or ReportingEngine()
        self._plugins = plugins or PluginRuntime(config=self._config)
        self._logger = logger or get_logger("application")
        self._pipeline = ProcessingPipeline(self._logger)
        for registered in self._plugins.extensions(PluginCategory.DRAWING_INTERPRETER):
            self._drawing.registry.register_extension(registered.extension)

    @property
    def config(self) -> AppConfig:
        """Resolved configuration this service was wired with."""
        return self._config

    @property
    def repositories(self) -> Repositories:
        """Repositories backing this service (SDS-002 §8.9)."""
        return self._repos

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

        def interpret(cid: str) -> Outcome[Any]:
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

        def derive(cid: str) -> Outcome[Any]:
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

    # -- use case: import asset registry (SDS-004) -------------------------

    def import_asset_registry(
        self,
        project_id: str,
        path: Path,
        reader: XlsxAssetRegistryReader | None = None,
    ) -> Outcome[RegistryImport]:
        correlation_id = new_id()
        project = self._repos.projects.get(project_id)
        if project is None:
            return self._unknown_project(project_id, correlation_id)
        registered = self._ingestion.register_input(
            project, path, correlation_id=correlation_id
        )
        if not registered.success or registered.payload is None:
            return Outcome.fail(
                registered.error_code or InputError.code,
                registered.message,
                correlation_id=correlation_id,
                remediation=registered.remediation,
            )
        source = registered.payload
        try:
            result = (reader or XlsxAssetRegistryReader()).read(source)
        except InputError as error:
            self._logger.error(
                str(error),
                operation="import-asset-registry",
                project_id=project_id,
                correlation_id=correlation_id,
                error_code=error.code,
            )
            return Outcome.from_error(error, correlation_id=correlation_id)
        self._repos.sources.add(source)
        for asset in result.assets:
            self._repos.assets.add(asset)
        self._logger.audit(
            f"Asset registry imported: {len(result.assets)} asset(s), "
            f"{result.skipped_rows} row(s) skipped",
            operation="import-asset-registry",
            project_id=project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(
            result,
            correlation_id=correlation_id,
            message=(
                f"{len(result.assets)} asset(s) imported, "
                f"{result.skipped_rows} row(s) skipped"
            ),
        )

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
        # SDS-005 §5: None -> standard pack; [] -> caller opts out.
        all_rules = list(rules) if rules is not None else standard_rules()
        all_rules.extend(
            self._conforming_extensions(
                PluginCategory.VALIDATION_RULE,
                # mypy rejects a protocol class where type[T] is expected; the
                # protocol is runtime_checkable and only used for isinstance.
                ValidationRule,  # type: ignore[type-abstract]
                correlation_id,
            )
        )
        project_assets = self._assets_for(project_id)
        context = ValidationContext(
            project=project,
            snapshots=self._snapshots_for(project_id),
            assets=project_assets,
            relations=self._relations_among(project_assets),
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
        all_formatters.extend(
            self._conforming_extensions(
                PluginCategory.REPORT_PROVIDER,
                # Same protocol-class limitation as validate_project above.
                ReportFormatter,  # type: ignore[type-abstract]
                correlation_id,
            )
        )
        view = self._reporting.compose(
            project=project,
            sources=self._sources_for(project_id),
            snapshots=self._snapshots_for(project_id),
            assets=self._assets_for(project_id),
            results=self._validation_results_for(project_id),
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

    def _conforming_extensions[T](
        self,
        category: PluginCategory,
        contract: type[T],
        correlation_id: str,
    ) -> list[T]:
        """Plugin extensions that actually satisfy the contract they claim.

        A plugin's extension is an arbitrary object, so it is checked against
        the runtime-checkable protocol before use. One that does not conform
        is skipped with a diagnostic rather than being trusted and failing
        later inside a rule or formatter loop (SDS-002 §10.5).
        """
        conforming: list[T] = []
        for registered in self._plugins.extensions(category):
            if isinstance(registered.extension, contract):
                conforming.append(registered.extension)
                continue
            self._logger.error(
                f"Plugin '{registered.manifest.plugin_id}' registered a "
                f"{category} extension that does not satisfy "
                f"{contract.__name__}; skipping it",
                operation="load-extension",
                correlation_id=correlation_id,
                error_code=InfrastructureError.code,
                plugin_id=registered.manifest.plugin_id,
                plugin_version=registered.manifest.version,
            )
        return conforming

    # Every read below is scoped to one project. Repositories span all
    # projects, so an unscoped list() would leak another project's data into
    # this project's validation context or report.

    def _sources_for(self, project_id: str) -> list[SourceInput]:
        return [
            source
            for source in self._repos.sources.list()
            if source.project_id == project_id
        ]

    def _snapshots_for(self, project_id: str) -> list[DrawingSnapshot]:
        return [
            snapshot
            for snapshot in self._repos.snapshots.list()
            if snapshot.project_id == project_id
        ]

    def _assets_for(self, project_id: str) -> list[Asset]:
        return [
            asset
            for asset in self._repos.assets.list()
            if asset.project_id == project_id
        ]

    def _relations_among(self, assets: list[Asset]) -> list[AssetRelation]:
        """Relations whose both endpoints are assets of the same project.

        A relation carries no project of its own; it belongs to a project
        through the assets it links (SDS-002 §9.3). Requiring both endpoints
        keeps a relation that spans projects out of either project's context
        rather than showing it in both.
        """
        asset_ids = {asset.asset_id for asset in assets}
        return [
            relation
            for relation in self._repos.relations.list()
            if relation.from_asset_id in asset_ids and relation.to_asset_id in asset_ids
        ]

    def _validation_results_for(self, project_id: str) -> list[ValidationResult]:
        """Findings emitted by validation runs of one project.

        A finding references its run, not its project, so the project's runs
        are resolved first (SDS-002 §9.3).
        """
        run_ids = {
            run.run_id
            for run in self._repos.validation_runs.list()
            if run.project_id == project_id
        }
        return [
            result
            for result in self._repos.validation_results.list()
            if result.run_id in run_ids
        ]

    def _unknown_project(self, project_id: str, correlation_id: str) -> Outcome[Any]:
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
