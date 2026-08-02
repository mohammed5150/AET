"""Command-line presentation layer (SDS-002 §8.1).

The CLI routes user intent into application use cases and converts internal
outcomes into user-understandable messages (SDS-002 §12.4). It performs no
parsing, domain calculation, or persistence work itself.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app import __version__
from app.core.outcome import Outcome
from app.services.use_cases import ApplicationService


def build_service() -> ApplicationService:
    """Wire the default application service."""
    return ApplicationService()


def _print_failure(outcome: Outcome) -> None:
    message = f"error [{outcome.error_code}]: {outcome.message}"
    if outcome.remediation:
        message = f"{message}\nhint: {outcome.remediation}"
    print(message, file=sys.stderr)


def _run(args: argparse.Namespace) -> int:
    service = build_service()
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

    validated = service.validate_project(project.project_id)
    if not validated.success or validated.payload is None:
        _print_failure(validated)
        return 1
    print(f"Validation findings: {len(validated.payload.results)}")

    reported = service.generate_report(project.project_id)
    if not reported.success or reported.payload is None:
        _print_failure(reported)
        return 1
    _, artifacts = reported.payload
    for artifact in artifacts:
        print()
        print(artifact.content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aet",
        description="Airfield Ground Lighting Engineering Toolkit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the drawing-to-report pipeline over source files",
    )
    run_parser.add_argument("files", nargs="+", help="Source drawing files")
    run_parser.add_argument("--name", default="Untitled Project", help="Project name")
    run_parser.set_defaults(handler=_run)

    version_parser = subparsers.add_parser("version", help="Show the AET version")
    version_parser.set_defaults(
        handler=lambda args: (print(f"aet {__version__}"), 0)[1]
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
