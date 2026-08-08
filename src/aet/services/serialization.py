"""Generic dataclass/document conversion for persistence (SDS-013).

Domain models are plain dataclasses, so a store can be written once for all of
them rather than nine times by hand. Decoding resolves each field's declared
type with :func:`typing.get_type_hints`, which is why the domain modules keep
their model imports at runtime rather than inside ``TYPE_CHECKING`` blocks
(ADR-002 / SDS-012's lint decisions).
"""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


def to_document(instance: Any) -> Any:
    """Convert a dataclass instance into JSON-compatible primitives."""
    if is_dataclass(instance) and not isinstance(instance, type):
        return {
            field.name: to_document(getattr(instance, field.name))
            for field in fields(instance)
        }
    if isinstance(instance, Enum):
        return instance.value
    if isinstance(instance, datetime):
        return instance.isoformat()
    # After datetime, which is itself a date: a timestamp must keep its time.
    if isinstance(instance, date):
        return instance.isoformat()
    if isinstance(instance, list | tuple):
        return [to_document(item) for item in instance]
    if isinstance(instance, dict):
        return {str(key): to_document(value) for key, value in instance.items()}
    return instance


def from_document[T](model: type[T], document: Any) -> T:
    """Rebuild a dataclass instance from the primitives ``to_document`` emits."""
    if not isinstance(document, dict):
        raise TypeError(
            f"Expected a mapping for {model.__name__}, got {type(document)}"
        )
    hints = get_type_hints(model)
    values = {
        field.name: _decode(hints[field.name], document[field.name])
        for field in fields(model)  # type: ignore[arg-type]
        # A field absent from the document keeps its default, so a model that
        # gains a field can still read rows written before it existed.
        if field.name in document
    }
    return model(**values)


def _decode(declared: Any, value: Any) -> Any:
    if value is None:
        return None
    declared = _without_none(declared)
    origin = get_origin(declared)
    if origin in (list, tuple):
        (item_type,) = get_args(declared)[:1] or (Any,)
        decoded = [_decode(item_type, item) for item in value]
        return tuple(decoded) if origin is tuple else decoded
    if origin is dict:
        args = get_args(declared)
        value_type = args[1] if len(args) == 2 else Any
        return {key: _decode(value_type, item) for key, item in value.items()}
    if isinstance(declared, type):
        if is_dataclass(declared):
            return from_document(declared, value)
        if issubclass(declared, Enum):
            return declared(value)
        if declared is datetime:
            return datetime.fromisoformat(value)
        if declared is date:
            return date.fromisoformat(value)
    return value


def _without_none(declared: Any) -> Any:
    """``X | None`` reduced to ``X``; anything else returned unchanged."""
    # `X | None` yields types.UnionType; Optional[X] yields typing.Union.
    if get_origin(declared) in (types.UnionType, Union):
        remaining = [arg for arg in get_args(declared) if arg is not type(None)]
        if len(remaining) == 1:
            return remaining[0]
    return declared
