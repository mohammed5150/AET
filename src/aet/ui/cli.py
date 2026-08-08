"""Command-line presentation layer (SDS-002 §8.1).

The CLI routes user intent into application use cases and converts internal
outcomes into user-understandable messages (SDS-002 §12.4). It performs no
parsing, domain calculation, or persistence work itself.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aet import __version__
from aet.core.config import AppConfig
from aet.core.errors import AETError, WorkflowError
from aet.core.logging import LEVEL_NAMES, configure_logging
from aet.core.outcome import Outcome
from aet.models.project import Project
from aet.services.persistence import attach_audit_sink
from aet.services.sqlite import connect, sqlite_repositories
from aet.services.use_cases import ApplicationService


def build_service(config: AppConfig | None = None) -> ApplicationService:
    """Wire the application service, its store, and its audit sink."""
    resolved = config or AppConfig.from_env()
    repositories = (
        sqlite_repositories(connect(resolved.database))
        if resolved.database is not None
        else None
    )
    service = ApplicationService(repositories=repositories, config=resolved)
    attach_audit_sink(service.repositories)
    return service


def resolve_config(args: argparse.Namespace) -> AppConfig:
    """Layer CLI flags over the environment-resolved configuration."""
    return AppConfig.from_env().with_overrides(
        log_level=args.log_level,
        log_dir=Path(args.log_dir) if args.log_dir else None,
        data_dir=Path(args.data_dir) if args.data_dir else None,
        database=Path(args.database) if args.database else None,
    )


def _print_error(code: str, message: str, remediation: str | None = None) -> None:
    text = f"error [{code}]: {message}"
    if remediation:
        text = f"{text}\nhint: {remediation}"
    print(text, file=sys.stderr)


def _print_failure(outcome: Outcome[Any]) -> None:
    _print_error(
        outcome.error_code or "AET_ERROR", outcome.message, outcome.remediation
    )


def _require_database(config: AppConfig) -> None:
    """Refuse a stateful command with nowhere to keep state (SDS-015 §4)."""
    if config.database is None:
        raise WorkflowError(
            "This command needs a database to read and write project state",
            remediation=(
                "Pass --database PATH, or set AET_DATABASE. Use `aet run` for a "
                "one-shot pipeline that keeps nothing."
            ),
        )


def _resolve_project(service: ApplicationService, token: str) -> Project:
    """Find a project by identifier, or by name when that is unambiguous.

    Identifiers are generated, so requiring one would mean copying a 32-digit
    string between commands. A name is what an operator actually has.
    """
    found = service.repositories.projects.get(token)
    if found is not None:
        return found
    matches = [
        project
        for project in service.repositories.projects.list()
        if project.name == token
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise WorkflowError(
            f"No project matches '{token}'",
            remediation="List projects with `aet project list`.",
        )
    # Names are not unique, so an ambiguous one is reported rather than
    # resolved by picking the first (SDS-015 §5).
    raise WorkflowError(
        f"'{token}' matches {len(matches)} projects",
        remediation=(
            "Use the project identifier: "
            + ", ".join(project.project_id for project in matches[:3])
        ),
    )


def _project_create(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    created = service.create_project(args.name, args.description)
    if not created.success or created.payload is None:
        _print_failure(created)
        return 1
    print(f"{created.payload.project_id}  {created.payload.name}")
    return 0


def _project_list(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    projects = service.repositories.projects.list()
    if not projects:
        print("No projects yet. Create one with `aet project create NAME`.")
        return 0
    for project in projects:
        assets = len(service.repositories.assets.list_for_project(project.project_id))
        print(f"{project.project_id}  {project.name}  ({assets} asset(s))")
    return 0


def _import(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    project = _resolve_project(service, args.project)
    for file_path in args.files:
        imported = service.import_drawing(project.project_id, Path(file_path))
        if not imported.success:
            _print_failure(imported)
            return 1
        print(f"Imported drawing {file_path}")
    for registry in args.registry or []:
        imported_registry = service.import_asset_registry(
            project.project_id, Path(registry)
        )
        if not imported_registry.success:
            _print_failure(imported_registry)
            return 1
        print(f"Imported registry {registry}: {imported_registry.message}")
    return 0


def _process(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    project = _resolve_project(service, args.project)
    processed = service.process_drawings(project.project_id)
    if not processed.success or processed.payload is None:
        _print_failure(processed)
        return 1
    for record in processed.payload.records:
        print(f"Stage {record.stage}: {record.status}")
    return 0


def _validate(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    project = _resolve_project(service, args.project)
    validated = service.validate_project(project.project_id)
    if not validated.success or validated.payload is None:
        _print_failure(validated)
        return 1
    failures = 0
    for result in validated.payload.results:
        status = "passed" if result.passed else "failed"
        if not result.passed:
            failures += 1
        print(f"{result.rule_id:32} {result.severity:8} {status}  {result.message}")
    # A non-zero status for findings lets a pipeline gate on validation.
    return 2 if failures else 0


def _report(args: argparse.Namespace, config: AppConfig) -> int:
    _require_database(config)
    service = build_service(config)
    project = _resolve_project(service, args.project)
    reported = service.generate_report(project.project_id)
    if not reported.success or reported.payload is None:
        _print_failure(reported)
        return 1
    _, artifacts = reported.payload
    for artifact in artifacts:
        print(artifact.content)
    return 0


def _run(args: argparse.Namespace, config: AppConfig) -> int:
    service = build_service(config)
    created = service.create_project(args.name)
    if not created.success or created.payload is None:
        _print_failure(created)
        return 1
    project = created.payload
    print(f"Created project '{project.name}' ({project.project_id})")

    for file_path in args.files:
        imported = service.import_drawing(project.project_id, Path(file_path))
        if not imported.success:
            _print_failure(imported)
            return 1
        print(f"Imported {file_path}")

    processed = service.process_drawings(project.project_id)
    if not processed.success or processed.payload is None:
        _print_failure(processed)
        return 1
    for record in processed.payload.records:
        print(f"Stage {record.stage}: {record.status}")

    if args.assets is not None:
        imported_assets = service.import_asset_registry(
            project.project_id, Path(args.assets)
        )
        if not imported_assets.success:
            _print_failure(imported_assets)
            return 1
        print(f"Asset registry: {imported_assets.message}")

    validated = service.validate_project(project.project_id)
    if not validated.success or validated.payload is None:
        _print_failure(validated)
        return 1
    print(f"Validation findings: {len(validated.payload.results)}")

    reported = service.generate_report(project.project_id, save=not args.no_save)
    if not reported.success or reported.payload is None:
        _print_failure(reported)
        return 1
    _, artifacts = reported.payload
    for artifact in artifacts:
        if artifact.location:
            print(f"Report written: {artifact.location}")
        else:
            print()
            print(artifact.content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aet",
        description="Airfield Ground Lighting Engineering Toolkit",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help=f"Log verbosity ({', '.join(LEVEL_NAMES)}); overrides AET_LOG_LEVEL",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Directory for aet.log and audit.log; overrides AET_LOG_DIR",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory for generated artifacts; overrides AET_DATA_DIR",
    )
    parser.add_argument(
        "--database",
        default=None,
        help=(
            "SQLite file to persist project state in; overrides AET_DATABASE. "
            "Without it nothing survives the run"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the drawing-to-report pipeline over source files",
    )
    run_parser.add_argument("files", nargs="+", help="Source drawing files")
    run_parser.add_argument("--name", default="Untitled Project", help="Project name")
    run_parser.add_argument(
        "--assets",
        default=None,
        help="Asset registry .xlsx to import after drawing processing",
    )
    run_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print the report to stdout instead of writing it to output/",
    )
    run_parser.set_defaults(handler=_run)

    project_parser = subparsers.add_parser("project", help="Create and list projects")
    project_actions = project_parser.add_subparsers(dest="action", required=True)
    create_parser = project_actions.add_parser("create", help="Create a project")
    create_parser.add_argument("name", help="Project name")
    create_parser.add_argument("--description", default="", help="Project description")
    create_parser.set_defaults(handler=_project_create)
    list_parser = project_actions.add_parser("list", help="List known projects")
    list_parser.set_defaults(handler=_project_list)

    import_parser = subparsers.add_parser(
        "import", help="Register drawings and asset registries with a project"
    )
    import_parser.add_argument("project", help="Project name or identifier")
    import_parser.add_argument("files", nargs="*", help="Drawing files to register")
    import_parser.add_argument(
        "--registry", action="append", help="Asset registry .xlsx to import"
    )
    import_parser.set_defaults(handler=_import)

    process_parser = subparsers.add_parser(
        "process", help="Interpret drawings and derive assets"
    )
    process_parser.add_argument("project", help="Project name or identifier")
    process_parser.set_defaults(handler=_process)

    validate_parser = subparsers.add_parser(
        "validate", help="Run the validation rules; exits 2 when a rule fails"
    )
    validate_parser.add_argument("project", help="Project name or identifier")
    validate_parser.set_defaults(handler=_validate)

    report_parser = subparsers.add_parser("report", help="Generate a project report")
    report_parser.add_argument("project", help="Project name or identifier")
    report_parser.set_defaults(handler=_report)

    version_parser = subparsers.add_parser("version", help="Show the AET version")
    version_parser.set_defaults(handler=_version)
    return parser


def _version(args: argparse.Namespace, config: AppConfig) -> int:
    print(f"aet {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace, AppConfig], int] = args.handler
    try:
        config = resolve_config(args)
        configure_logging(config)
        # The handler is inside the boundary too: opening the store is an
        # expected failure, and a bad --database must read as an error with
        # remediation, not as a traceback (SDS-002 §12.4).
        return handler(args, config)
    except AETError as error:
        _print_error(error.code, str(error), error.remediation)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
