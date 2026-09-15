"""Shared editable parameters and defaults for form rendering and compilation."""

from __future__ import annotations

from typing import Final

from albumentationsx_plugin.core import (
    DEFAULT_BRIGHTNESS_RANGE,
    DEFAULT_CONTRAST_RANGE,
    DEFAULT_CROP_SIZE,
    DEFAULT_TRANSFORM_PROBABILITY,
    FormFieldSchema,
    TransformCatalogProvider,
)
from albumentationsx_plugin.core.serialization import normalize_json_value

SCHEMA_STATUS_JSON_FALLBACK: Final[str] = "json_fallback"


def executable_parameter_fields(
    *,
    selected_transform_name: str,
    catalog_provider: TransformCatalogProvider,
    parameter_fields: tuple[FormFieldSchema, ...],
) -> tuple[FormFieldSchema, ...]:
    externally_resolved_parameter_names = _externally_resolved_parameter_names(
        selected_transform_name,
        catalog_provider=catalog_provider,
    )
    return tuple(
        _executable_parameter_field(selected_transform_name=selected_transform_name, field=field)
        for field in parameter_fields
        if _is_executable_parameter(field)
        if field.name not in externally_resolved_parameter_names
    )


def _externally_resolved_parameter_names(
    transform_name: str,
    *,
    catalog_provider: TransformCatalogProvider,
) -> frozenset[str]:
    capability = catalog_provider.get_transform_capability(transform_name)
    if capability is None:
        return frozenset()
    return frozenset(
        requirement.parameter_name
        for requirement in capability.external_inputs
        if requirement.parameter_name is not None
    )


def _is_executable_parameter(field: FormFieldSchema) -> bool:
    if is_json_fallback_parameter(field):
        return not field.required
    return True


def is_json_fallback_parameter(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") == SCHEMA_STATUS_JSON_FALLBACK


def _executable_parameter_field(*, selected_transform_name: str, field: FormFieldSchema) -> FormFieldSchema:
    if field.name == "p":
        return FormFieldSchema(
            name=field.name,
            kind=field.kind,
            label=field.label,
            required=False,
            default=DEFAULT_TRANSFORM_PROBABILITY,
            min_value=field.min_value,
            max_value=field.max_value,
            choices=field.choices,
            item_schema=field.item_schema,
            help_text=field.help_text,
            metadata=field.metadata,
        )
    if selected_transform_name == "RandomBrightnessContrast" and field.name == "brightness_range":
        return _field_with_default(field, [DEFAULT_BRIGHTNESS_RANGE[0], DEFAULT_BRIGHTNESS_RANGE[1]])
    if selected_transform_name == "RandomBrightnessContrast" and field.name == "contrast_range":
        return _field_with_default(field, [DEFAULT_CONTRAST_RANGE[0], DEFAULT_CONTRAST_RANGE[1]])
    if selected_transform_name == "RandomCrop" and field.name in {"height", "width"}:
        return _field_with_default(field, DEFAULT_CROP_SIZE)
    return field


def _field_with_default(field: FormFieldSchema, default: object) -> FormFieldSchema:
    json_default = normalize_json_value(default)
    return FormFieldSchema(
        name=field.name,
        kind=field.kind,
        label=field.label,
        required=False,
        default=json_default,
        min_value=field.min_value,
        max_value=field.max_value,
        choices=field.choices,
        item_schema=field.item_schema,
        help_text=field.help_text,
        metadata=field.metadata,
    )
