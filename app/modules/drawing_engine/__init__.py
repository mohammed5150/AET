"""Drawing interpretation module (SDS-002 §8.5, SDS-003, SDS-006)."""

from app.modules.drawing_engine.dwg import (
    DwgConversionInterpreter,
    DwgConverter,
    LibreDwgConverter,
    OdaFileConverter,
    default_converters,
)
from app.modules.drawing_engine.dxf import DxfInterpreter
from app.modules.drawing_engine.engine import (
    DrawingEngine,
    DrawingInterpreter,
    PassthroughInterpreter,
)
from app.modules.drawing_engine.registry import (
    InterpreterRegistry,
    default_registry,
)

__all__ = [
    "DrawingEngine",
    "DrawingInterpreter",
    "DwgConversionInterpreter",
    "DwgConverter",
    "DxfInterpreter",
    "InterpreterRegistry",
    "LibreDwgConverter",
    "OdaFileConverter",
    "PassthroughInterpreter",
    "default_converters",
    "default_registry",
]
