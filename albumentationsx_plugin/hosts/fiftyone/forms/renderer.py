"""Render host-neutral form schemas into FiftyOne operator input objects."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, TypeGuard, cast

import fiftyone.operators.types as types

from albumentationsx_plugin.core import FieldKind, FormFieldSchema, HostAdapterError, JSONValue

SUPPORTED_FIELD_KINDS: Final[frozenset[FieldKind]] = frozenset(
    {
        FieldKind.BOOLEAN,
        FieldKind.INTEGER,
        FieldKind.FLOAT,
        FieldKind.STRING,
        FieldKind.ENUM,
        FieldKind.NUMBER_RANGE,
        FieldKind.LIST,
        FieldKind.JSON,
    },
)
UNSUPPORTED_REQUIRED_SCHEMA_STATUS: Final[str] = "unsupported_required"


class UnsupportedFormFieldError(HostAdapterError):
    """Raised when a neutral form field cannot be rendered in the FiftyOne App."""

    def __init__(self, field: FormFieldSchema) -> None:
        super().__init__(
            host="fiftyone",
            message=f"FiftyOne form renderer does not support {field.kind.value} field '{field.name}'.",
            context={
                "field_name": field.name,
                "field_kind": field.kind.value,
            },
        )


@dataclass(frozen=True, slots=True)
class FiftyOneFormRenderer:
    """Converts reusable form schema objects into FiftyOne operator fields."""

    def render(self, fields: Iterable[FormFieldSchema]) -> types.Object:
        """Render fields into a new FiftyOne object."""

        inputs = types.Object()
        self.render_into(inputs, fields)
        return inputs

    def render_into(self, target: types.Object, fields: Iterable[FormFieldSchema]) -> types.Object:
        """Render fields into an existing FiftyOne object and return it."""

        for field in fields:
            self.render_field(target, field)
        return target

    def render_field(self, target: types.Object, field: FormFieldSchema) -> None:
        """Render one field into the target object."""

        if field.kind not in SUPPORTED_FIELD_KINDS:
            raise UnsupportedFormFieldError(field)

        kwargs = _property_kwargs(field)
        match field.kind:
            case FieldKind.BOOLEAN:
                target.bool(field.name, **kwargs)
            case FieldKind.INTEGER:
                target.int(field.name, min=field.min_value, max=field.max_value, **kwargs)
            case FieldKind.FLOAT:
                target.float(field.name, min=field.min_value, max=field.max_value, **kwargs)
            case FieldKind.STRING:
                target.str(field.name, allow_empty=not field.required, **kwargs)
            case FieldKind.ENUM:
                target.enum(field.name, _enum_values(field), **kwargs)
            case FieldKind.NUMBER_RANGE:
                target.tuple(
                    field.name,
                    _number_type_from_item_schema(field.item_schema),
                    _number_type_from_item_schema(field.item_schema),
                    **kwargs,
                )
            case FieldKind.LIST:
                target.list(
                    field.name,
                    _type_from_item_schema(field.item_schema),
                    min_items=_list_min_items(field),
                    max_items=_list_max_items(field),
                    **kwargs,
                )
            case FieldKind.JSON:
                target.str(
                    field.name,
                    allow_empty=not field.required,
                    default=_json_string_default(field),
                    **_json_property_kwargs(field, kwargs),
                )
            case _:
                raise UnsupportedFormFieldError(field)


def render_form(fields: Iterable[FormFieldSchema]) -> types.Object:
    """Render a neutral field sequence into a FiftyOne operator object."""

    return FiftyOneFormRenderer().render(fields)


def _property_kwargs(field: FormFieldSchema) -> dict[str, object]:
    kwargs: dict[str, object] = {"required": field.required}
    if field.label is not None:
        kwargs["label"] = field.label
    description = _field_description(field)
    if description is not None:
        kwargs["description"] = description
    if field.default is not None:
        kwargs["default"] = field.default
    if _is_unsupported_required_schema(field):
        kwargs["invalid"] = True
        kwargs["error_message"] = "This required parameter cannot be rendered safely yet."
        kwargs["view"] = types.View(read_only=True)
    return kwargs


def _field_description(field: FormFieldSchema) -> str | None:
    parts = [field.help_text] if field.help_text is not None else []
    constraint_description = _constraint_description(field)
    if constraint_description is not None:
        parts.append(constraint_description)
    return " ".join(parts) if parts else None


def _constraint_description(field: FormFieldSchema) -> str | None:
    constraints = _metadata_mapping(field, "constraints")
    if not constraints:
        return None

    parts = [
        description
        for field_name, formatter in _constraint_formatters()
        if (description := _constraint_part(constraints, field_name, formatter)) is not None
    ]
    return "Constraints: " + ", ".join(parts) + "." if parts else None


def _constraint_formatters() -> tuple[tuple[str, str], ...]:
    return (
        ("ge", ">="),
        ("gt", ">"),
        ("le", "<="),
        ("lt", "<"),
        ("min_value", "min"),
        ("max_value", "max"),
        ("min_length", "min length"),
        ("max_length", "max length"),
        ("multiple_of", "multiple of"),
        ("pattern", "pattern"),
    )


def _constraint_part(constraints: Mapping[str, object], field_name: str, formatter: str) -> str | None:
    value = constraints.get(field_name)
    if value is None:
        return None
    return f"{formatter} {_format_constraint_value(value)}"


def _format_constraint_value(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _enum_values(field: FormFieldSchema) -> list[str | int | float | bool | None]:
    values: list[str | int | float | bool | None] = []
    for choice in field.choices:
        if not _is_supported_enum_value(choice):
            raise HostAdapterError(
                host="fiftyone",
                message=f"FiftyOne enum field '{field.name}' has an unsupported choice value.",
                context={
                    "field_name": field.name,
                    "field_kind": field.kind.value,
                    "choice": choice,
                },
            )
        values.append(choice)
    return values


def _is_supported_enum_value(value: JSONValue) -> TypeGuard[str | int | float | bool | None]:
    return value is None or isinstance(value, str | int | float | bool)


def _json_property_kwargs(field: FormFieldSchema, kwargs: dict[str, object]) -> dict[str, object]:
    updated_kwargs = {**kwargs}
    updated_kwargs.pop("default", None)
    return updated_kwargs


def _json_string_default(field: FormFieldSchema) -> str:
    if field.default is None:
        return ""
    return json.dumps(field.default, sort_keys=True)


def _type_from_item_schema(item_schema: object) -> types.BaseType:
    if not isinstance(item_schema, dict):
        return types.String()

    kind = item_schema.get("kind")
    match kind:
        case FieldKind.BOOLEAN.value:
            return types.Boolean()
        case FieldKind.INTEGER.value:
            return types.Number(int=True)
        case FieldKind.FLOAT.value:
            return types.Number(float=True)
        case FieldKind.STRING.value:
            return types.String()
        case _:
            return types.String()


def _number_type_from_item_schema(item_schema: object) -> types.Number:
    if isinstance(item_schema, dict) and item_schema.get("kind") == FieldKind.INTEGER.value:
        return types.Number(int=True)
    return types.Number(float=True)


def _list_min_items(field: FormFieldSchema) -> int | None:
    length = _list_length(field)
    if length is not None:
        return length
    constraints = _metadata_mapping(field, "constraints")
    min_length = constraints.get("min_length")
    return int(min_length) if isinstance(min_length, int | float) else None


def _list_max_items(field: FormFieldSchema) -> int | None:
    length = _list_length(field)
    if length is not None:
        return length
    constraints = _metadata_mapping(field, "constraints")
    max_length = constraints.get("max_length")
    return int(max_length) if isinstance(max_length, int | float) else None


def _list_length(field: FormFieldSchema) -> int | None:
    if not isinstance(field.item_schema, dict):
        return None
    length = field.item_schema.get("length")
    return int(length) if isinstance(length, int | float) else None


def _metadata_mapping(field: FormFieldSchema, key: str) -> dict[str, object]:
    value = field.metadata.get(key)
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _is_unsupported_required_schema(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") == UNSUPPORTED_REQUIRED_SCHEMA_STATUS
