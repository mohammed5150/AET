"""DWG support via external conversion to DXF (SDS-006).

Binary DWG parsing stays out of scope; instead a converter backend (ODA
File Converter or GNU LibreDWG's ``dwg2dxf``) produces a transient DXF
that the SDS-003 interpreter consumes. The snapshot remains the durable
artifact and carries DWG provenance.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from aet.core.errors import InputError, ProcessingError
from aet.core.logging import StructuredLogger, get_logger
from aet.models.drawing import DrawingSnapshot
from aet.models.project import SourceInput
from aet.modules.drawing_engine.dxf import DxfInterpreter

_CONVERT_TIMEOUT_SECONDS = 300
_DIAGNOSTIC_LIMIT = 500


class DwgConverter(Protocol):
    """Converter backend contract (SDS-006 §3)."""

    name: str

    def available(self) -> bool:
        """Whether this backend can run in the current environment."""
        ...

    def convert(self, dwg_path: Path, output_dir: Path) -> Path:
        """Convert one DWG to DXF, returning the produced file."""
        ...


def _run(command: list[str], failure_context: str) -> None:
    """Run one converter invocation, mapping any failure to ProcessingError.

    The command is built by this module from an operator-configured converter
    path (``ODA_FILE_CONVERTER`` / ``DWG2DXF``, else a ``PATH`` lookup) and
    file paths — never from drawing content. No shell is involved, so the
    arguments cannot be reinterpreted as a command.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - operator-configured path, no shell
            command,
            capture_output=True,
            text=True,
            timeout=_CONVERT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProcessingError(f"{failure_context}: {exc}") from exc
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout or "").strip()
        raise ProcessingError(
            f"{failure_context} (exit {completed.returncode}): "
            f"{diagnostic[:_DIAGNOSTIC_LIMIT]}"
        )


class OdaFileConverter:
    """ODA File Converter backend (SDS-006 §3.1)."""

    name = "oda"

    def _executable(self) -> str | None:
        configured = os.environ.get("ODA_FILE_CONVERTER")
        if configured:
            return configured if Path(configured).is_file() else None
        return shutil.which("ODAFileConverter")

    def available(self) -> bool:
        return self._executable() is not None

    def convert(self, dwg_path: Path, output_dir: Path) -> Path:
        executable = self._executable()
        if executable is None:
            raise ProcessingError("ODA File Converter executable not found")
        # ODA's CLI is directory-based: stage the input in its own folder.
        staging = output_dir / "oda-in"
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dwg_path, staging / dwg_path.name)
        _run(
            [
                executable,
                str(staging),
                str(output_dir),
                "ACAD2018",
                "DXF",
                "0",
                "1",
                dwg_path.name,
            ],
            f"ODA File Converter failed for {dwg_path}",
        )
        produced = output_dir / f"{dwg_path.stem}.dxf"
        if not produced.is_file():
            raise ProcessingError(f"ODA File Converter produced no DXF for {dwg_path}")
        return produced


class LibreDwgConverter:
    """GNU LibreDWG ``dwg2dxf`` backend (SDS-006 §3.2)."""

    name = "libredwg"

    def _executable(self) -> str | None:
        configured = os.environ.get("DWG2DXF")
        if configured:
            return configured if Path(configured).is_file() else None
        return shutil.which("dwg2dxf")

    def available(self) -> bool:
        return self._executable() is not None

    def convert(self, dwg_path: Path, output_dir: Path) -> Path:
        executable = self._executable()
        if executable is None:
            raise ProcessingError("dwg2dxf executable not found")
        produced = output_dir / f"{dwg_path.stem}.dxf"
        _run(
            [executable, "-o", str(produced), str(dwg_path)],
            f"dwg2dxf failed for {dwg_path}",
        )
        if not produced.is_file():
            raise ProcessingError(f"dwg2dxf produced no DXF for {dwg_path}")
        return produced


def default_converters() -> list[DwgConverter]:
    """Default backend chain, in selection order (SDS-006 §4)."""
    return [OdaFileConverter(), LibreDwgConverter()]


class DwgConversionInterpreter:
    """Interprets DWG sources by converting to DXF first (SDS-006 §4)."""

    supported_formats = ("dwg",)

    def __init__(
        self,
        converters: list[DwgConverter] | None = None,
        dxf_interpreter: DxfInterpreter | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._converters = (
            converters if converters is not None else default_converters()
        )
        self._dxf = dxf_interpreter or DxfInterpreter()
        self._logger = logger or get_logger("dwg-converter")

    def interpret(self, source: SourceInput) -> DrawingSnapshot:
        converter = next(
            (backend for backend in self._converters if backend.available()),
            None,
        )
        if converter is None:
            raise InputError(
                f"No DWG converter backend is available for {source.path}",
                remediation=(
                    "Install ODA File Converter (set ODA_FILE_CONVERTER) or "
                    "GNU LibreDWG's dwg2dxf (set DWG2DXF), or convert the "
                    "file to DXF manually and re-import it."
                ),
            )
        with tempfile.TemporaryDirectory(prefix="aet-dwg-") as workdir:
            produced = converter.convert(Path(source.path), Path(workdir))
            self._logger.info(
                f"Converted {source.path} via {converter.name}",
                stage="interpretation",
                project_id=source.project_id,
            )
            snapshot = self._dxf.interpret(replace(source, path=str(produced)))
        # Restore DWG provenance: the converted DXF is transient (§5).
        snapshot.metadata["source_path"] = source.path
        snapshot.metadata["source_hash"] = source.file_hash
        snapshot.metadata["converter"] = converter.name
        return snapshot
