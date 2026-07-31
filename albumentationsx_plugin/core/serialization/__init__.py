"""JSON serialization helpers for host-neutral plugin contracts.

Core DTOs cross three boundaries: FiftyOne operator inputs, persisted run
manifests, and unit-test fixtures. Keeping serialization strict at this layer
prevents backend or host adapters from smuggling runtime objects into manifests.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, TypeAlias

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]


def normalize_json_value(value: object) -> JSONValue:
    """Return a JSON-compatible copy of a value.

    Tuples are normalized to lists because manifests and operator payloads are
    JSON objects. Non-finite floats and arbitrary Python objects are rejected so
    invalid data fails at the boundary closest to where it was created.
    """

    if value is None or isinstance(value, str | bool | int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON values cannot contain NaN or infinite floats")
        return value

    if isinstance(value, Mapping):
        normalized: JSONDict = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            normalized[key] = normalize_json_value(nested_value)
        return normalized

    if isinstance(value, list | tuple):
        return [normalize_json_value(nested_value) for nested_value in value]

    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def normalize_json_mapping(value: Mapping[str, object] | None) -> JSONDict:
    """Return a JSON-compatible dictionary copy."""

    if value is None:
        return {}

    normalized = normalize_json_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("Expected a JSON object")
    return normalized


def string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Normalize an optional string list into an immutable tuple."""

    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise TypeError(f"{field_name} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must contain only strings")
    return tuple(value)


def mapping_tuple(value: object, field_name: str) -> tuple[JSONDict, ...]:
    """Normalize an optional list of JSON objects into immutable dictionaries."""

    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise TypeError(f"{field_name} must be a list of JSON objects")

    normalized: list[JSONDict] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(f"{field_name} must contain only JSON objects")
        normalized.append(normalize_json_mapping(item))
    return tuple(normalized)


def require_str(value: object, field_name: str) -> str:
    """Return a non-empty string or raise a field-specific error."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def optional_str(value: object, field_name: str) -> str | None:
    """Return `None` or a non-empty string."""

    if value is None:
        return None
    return require_str(value, field_name)


def optional_float(value: object, field_name: str) -> float | None:
    """Return `None` or a finite float."""

    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise TypeError(f"{field_name} cannot be NaN or infinite")
    return number


def require_int(value: object, field_name: str) -> int:
    """Return an integer, rejecting booleans even though `bool` subclasses `int`."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    return value


def require_bool(value: object, field_name: str) -> bool:
    """Return a boolean value."""

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    """Return a mapping used as a source JSON object."""

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    return value
