"""Format-keyed interpreter registry (SDS-003 §4).

The drawing engine selects an interpreter by source format identity.
Drawing-interpreter plugin extensions declaring ``supported_formats`` are
registered through :meth:`InterpreterRegistry.register_extension`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.drawing_engine.dwg import DwgConversionInterpreter
from app.modules.drawing_engine.dxf import DxfInterpreter

if TYPE_CHECKING:
    from app.modules.drawing_engine.engine import DrawingInterpreter


class InterpreterRegistry:
    """Maps lowercase format identities to interpreter strategies."""

    def __init__(self) -> None:
        self._by_format: dict[str, DrawingInterpreter] = {}

    def register(self, format_id: str, interpreter: DrawingInterpreter) -> None:
        self._by_format[format_id.lower()] = interpreter

    def register_extension(self, extension: object) -> list[str]:
        """Register a plugin extension for each format it declares."""
        formats = [
            str(format_id).lower()
            for format_id in getattr(extension, "supported_formats", ())
        ]
        for format_id in formats:
            self._by_format[format_id] = extension  # type: ignore[assignment]
        return formats

    def lookup(self, format_id: str) -> DrawingInterpreter | None:
        return self._by_format.get(format_id.lower())

    def formats(self) -> list[str]:
        return sorted(self._by_format)


def default_registry() -> InterpreterRegistry:
    """Registry seeded with the built-in interpreters."""
    registry = InterpreterRegistry()
    registry.register("dxf", DxfInterpreter())
    registry.register("dwg", DwgConversionInterpreter())
    return registry
