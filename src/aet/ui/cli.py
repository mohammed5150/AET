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
from aet.core.errors import AETError
from aet.core.logging import LEVEL_NAMES, configure_logging
from aet.core.outcome import Outcome
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
