"""Render host-neutral form schemas into FiftyOne operator input objects."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, TypeGuard

import fiftyone.operators.types as types

from albumentationsx_plugin.core import FieldKind, FormFieldSchema, HostAdapterError, JSONValue

SUPPORTED_FIELD_KINDS: Final[frozenset[FieldKind]] = frozenset(
    {
        FieldKind.BOOLEAN,
        FieldKind.INTEGER,
        FieldKind.FLOAT,
        FieldKind.STRING,
        FieldKind.ENUM,
    },
)


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
            case _:
                raise UnsupportedFormFieldError(field)


def render_form(fields: Iterable[FormFieldSchema]) -> types.Object:
    """Render a neutral field sequence into a FiftyOne operator object."""

    return FiftyOneFormRenderer().render(fields)


def _property_kwargs(field: FormFieldSchema) -> dict[str, object]:
    kwargs: dict[str, object] = {"required": field.required}
    if field.label is not None:
        kwargs["label"] = field.label
    if field.help_text is not None:
        kwargs["description"] = field.help_text
    if field.default is not None:
        kwargs["default"] = field.default
    return kwargs


def _enum_values(field: FormFieldSchema) -> list[str | int | float | bool]:
    values: list[str | int | float | bool] = []
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


def _is_supported_enum_value(value: JSONValue) -> TypeGuard[str | int | float | bool]:
    return isinstance(value, str | int | float | bool)
