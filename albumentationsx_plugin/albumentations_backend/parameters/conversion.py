"""Convert albu-spec parameter metadata into host-neutral field schemas."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from albumentationsx_plugin.core import FieldKind, FormFieldSchema, JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping, normalize_json_value

SCHEMA_STATUS_SUPPORTED: Final[str] = "supported"
SCHEMA_STATUS_JSON_FALLBACK: Final[str] = "json_fallback"
SCHEMA_STATUS_UNSUPPORTED_REQUIRED: Final[str] = "unsupported_required"

REASON_SUPPORTED_TYPE_HINT: Final[str] = "supported_type_hint"
REASON_COMPLEX_OPTIONAL_PARAMETER: Final[str] = "complex_optional_parameter"
REASON_UNSUPPORTED_REQUIRED_PARAMETER: Final[str] = "unsupported_required_parameter"

SIMPLE_TYPE_HINTS: Final[dict[str, FieldKind]] = {
    "bool": FieldKind.BOOLEAN,
    "int": FieldKind.INTEGER,
    "float": FieldKind.FLOAT,
    "str": FieldKind.STRING,
}
NUMERIC_TYPE_HINTS: Final[frozenset[str]] = frozenset({"int", "float"})
JSON_FALLBACK_ITEM_SCHEMA: Final[Mapping[str, object]] = {"kind": FieldKind.JSON.value}

_TWO_ITEM_NUMERIC_TUPLE_RE: Final[re.Pattern[str]] = re.compile(r"^tuple\[(int|float), (int|float)\]$")
_HOMOGENEOUS_LIST_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:list\[(int|float|str)\]|tuple\[(int|float|str), \.\.\.\])$",
)
_FIXED_LIST_RE: Final[re.Pattern[str]] = re.compile(r"^tuple\[((?:int|float|str)(?:, (?:int|float|str))*)\]$")


def build_transform_parameter_schema(metadata: Any) -> tuple[FormFieldSchema, ...]:
    """Return neutral parameter fields for one albu-spec transform metadata object."""

    return tuple(
        build_parameter_field_schema(parameter, parameter_name=parameter_name)
        for parameter_name, parameter in _parameters(metadata).items()
    )


def build_parameter_field_schema(parameter: Any, *, parameter_name: str | None = None) -> FormFieldSchema:
    """Return a neutral field schema for one albu-spec parameter metadata object."""

    name = parameter_name or _parameter_name(parameter)
    type_hint = getattr(parameter, "type_hint", None)
    default = _json_default(parameter)
    required = is_parameter_required(parameter)
    metadata = _base_metadata(parameter, type_hint=type_hint)

    field_kind, choices, item_schema, status, reason_code = _field_shape(type_hint=type_hint, required=required)
    metadata["schema_status"] = status
    metadata["reason_code"] = reason_code

    return FormFieldSchema(
        name=name,
        kind=field_kind,
        label=_label_from_name(name),
        required=required,
        default=default,
        min_value=_constraint_min_value(getattr(parameter, "constraints", None)),
        max_value=_constraint_max_value(getattr(parameter, "constraints", None)),
        choices=choices,
        item_schema=item_schema,
        help_text=_parameter_description(parameter),
        metadata=metadata,
    )


def is_parameter_required(parameter: Any) -> bool:
    """Return whether the parameter must be supplied by a host UI or pipeline builder."""

    if _parameter_name(parameter) == "p":
        return False

    if getattr(parameter, "default", None) is not None:
        return False

    type_hint = getattr(parameter, "type_hint", None)
    if isinstance(type_hint, list):
        return None not in type_hint
    if isinstance(type_hint, str):
        return not _is_optional_type_hint(type_hint)
    return True


def _field_shape(
    *,
    type_hint: object,
    required: bool,
) -> tuple[FieldKind, tuple[JSONValue, ...], Mapping[str, object] | None, str, str]:
    if isinstance(type_hint, list) and _is_json_primitive_sequence(type_hint):
        return (
            FieldKind.ENUM,
            tuple(normalize_json_value(choice) for choice in type_hint),
            None,
            SCHEMA_STATUS_SUPPORTED,
            REASON_SUPPORTED_TYPE_HINT,
        )

    if not isinstance(type_hint, str):
        return _json_fallback_shape(required=required)

    normalized_type_hint = _strip_optional_type_hint(type_hint)
    simple_kind = SIMPLE_TYPE_HINTS.get(normalized_type_hint)
    if simple_kind is not None:
        return simple_kind, (), None, SCHEMA_STATUS_SUPPORTED, REASON_SUPPORTED_TYPE_HINT

    range_item_kind = _numeric_range_item_kind(normalized_type_hint)
    if range_item_kind is not None:
        return (
            FieldKind.NUMBER_RANGE,
            (),
            {"kind": range_item_kind.value},
            SCHEMA_STATUS_SUPPORTED,
            REASON_SUPPORTED_TYPE_HINT,
        )

    list_item_schema = _list_item_schema(normalized_type_hint)
    if list_item_schema is not None:
        return (
            FieldKind.LIST,
            (),
            list_item_schema,
            SCHEMA_STATUS_SUPPORTED,
            REASON_SUPPORTED_TYPE_HINT,
        )

    return _json_fallback_shape(required=required)


def _json_fallback_shape(*, required: bool) -> tuple[FieldKind, tuple[JSONValue, ...], Mapping[str, object], str, str]:
    if required:
        return (
            FieldKind.JSON,
            (),
            JSON_FALLBACK_ITEM_SCHEMA,
            SCHEMA_STATUS_UNSUPPORTED_REQUIRED,
            REASON_UNSUPPORTED_REQUIRED_PARAMETER,
        )
    return (
        FieldKind.JSON,
        (),
        JSON_FALLBACK_ITEM_SCHEMA,
        SCHEMA_STATUS_JSON_FALLBACK,
        REASON_COMPLEX_OPTIONAL_PARAMETER,
    )


def _numeric_range_item_kind(type_hint: str) -> FieldKind | None:
    tuple_match = _TWO_ITEM_NUMERIC_TUPLE_RE.match(type_hint)
    if tuple_match is not None:
        return _numeric_item_kind(tuple_match.groups())

    union_parts = type_hint.split(" | ")
    if len(union_parts) < 2:
        return None
    numeric_parts: list[str] = []
    for part in union_parts:
        tuple_match = _TWO_ITEM_NUMERIC_TUPLE_RE.match(part)
        if tuple_match is None:
            return None
        numeric_parts.extend(tuple_match.groups())
    return _numeric_item_kind(tuple(numeric_parts))


def _list_item_schema(type_hint: str) -> Mapping[str, object] | None:
    homogeneous_match = _HOMOGENEOUS_LIST_RE.match(type_hint)
    if homogeneous_match is not None:
        matched_type_hint = homogeneous_match.group(1) or homogeneous_match.group(2)
        item_kind = SIMPLE_TYPE_HINTS[matched_type_hint]
        return {"kind": item_kind.value}

    fixed_match = _FIXED_LIST_RE.match(type_hint)
    if fixed_match is None:
        return None

    item_type_hints = tuple(part.strip() for part in fixed_match.group(1).split(","))
    item_kind = _fixed_list_item_kind(item_type_hints)
    if item_kind is None:
        return None
    return {
        "kind": item_kind.value,
        "length": len(item_type_hints),
    }


def _fixed_list_item_kind(type_hints: tuple[str, ...]) -> FieldKind | None:
    if not type_hints:
        return None
    if all(type_hint == "str" for type_hint in type_hints):
        return FieldKind.STRING
    if all(type_hint in NUMERIC_TYPE_HINTS for type_hint in type_hints):
        return _numeric_item_kind(type_hints)
    return None


def _numeric_item_kind(type_hints: tuple[str, ...]) -> FieldKind:
    if any(type_hint == "float" for type_hint in type_hints):
        return FieldKind.FLOAT
    return FieldKind.INTEGER


def _parameters(metadata: Any) -> Mapping[str, Any]:
    parameters = getattr(metadata, "parameters", {})
    if isinstance(parameters, Mapping):
        return parameters
    return {}


def _base_metadata(parameter: Any, *, type_hint: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "albu-spec",
        "type_hint": _json_type_hint(type_hint),
    }
    constraints = _constraint_metadata(getattr(parameter, "constraints", None))
    if constraints:
        metadata["constraints"] = constraints
    return metadata


def _json_type_hint(type_hint: object) -> JSONValue:
    if isinstance(type_hint, list):
        return normalize_json_value(type_hint)
    if isinstance(type_hint, str):
        return type_hint
    return repr(type_hint)


def _json_default(parameter: Any) -> JSONValue:
    return normalize_json_value(getattr(parameter, "default", None))


def _parameter_name(parameter: Any) -> str:
    name = getattr(parameter, "name", "")
    return name if isinstance(name, str) and name else "<unknown>"


def _parameter_description(parameter: Any) -> str | None:
    description = getattr(parameter, "description", None)
    return description if isinstance(description, str) and description.strip() else None


def _label_from_name(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _is_json_primitive_sequence(value: list[object]) -> bool:
    return all(item is None or isinstance(item, str | int | float | bool) for item in value)


def _is_optional_type_hint(type_hint: str) -> bool:
    return (
        type_hint == "None" or type_hint.endswith(" | None") or type_hint.startswith("None | ") or " None]" in type_hint
    )


def _strip_optional_type_hint(type_hint: str) -> str:
    if type_hint.endswith(" | None"):
        return type_hint.removesuffix(" | None")
    if type_hint.startswith("None | "):
        return type_hint.removeprefix("None | ")
    return type_hint


def _constraint_min_value(constraints: Any) -> float | None:
    if constraints is None:
        return None
    for field_name in ("ge", "gt", "min_value"):
        value = getattr(constraints, field_name, None)
        if value is not None:
            return float(value)
    return None


def _constraint_max_value(constraints: Any) -> float | None:
    if constraints is None:
        return None
    for field_name in ("le", "lt", "max_value"):
        value = getattr(constraints, field_name, None)
        if value is not None:
            return float(value)
    return None


def _constraint_metadata(constraints: Any) -> JSONDict:
    if constraints is None:
        return {}

    constraint_values: dict[str, object] = {}
    for field_name in (
        "ge",
        "le",
        "gt",
        "lt",
        "min_length",
        "max_length",
        "multiple_of",
        "min_value",
        "max_value",
        "pattern",
    ):
        value = getattr(constraints, field_name, None)
        if value is not None:
            constraint_values[field_name] = value
    return normalize_json_mapping(constraint_values)
