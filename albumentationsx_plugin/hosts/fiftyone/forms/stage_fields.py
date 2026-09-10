"""Render editable transform parameters and stage controls."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from albumentationsx_plugin.core import (
    DEFAULT_CROP_SIZE,
    FIXED_TRANSFORM_NAMES,
    MAX_PIPELINE_STEPS,
    FieldKind,
    FormFieldSchema,
    TransformCatalogProvider,
    UnsupportedTransformError,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.core.serialization import normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    FIELD_TYPE_HEATMAP,
    SELECTED_LABEL_FIELDS_PARAM_NAME,
    AnnotationField,
    annotation_field_param_name,
    annotation_field_selection_is_explicit,
)
from albumentationsx_plugin.hosts.fiftyone.forms.defaults import (
    RandomCropDefaults,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_fields import (
    DEFAULT_DYNAMIC_TRANSFORM_NAME,
    PIPELINE_STAGE_ENABLED_LABEL,
    PIPELINE_STAGE_ORDER_LABEL,
    PROBABILITY_FIELD_NAME,
    RANDOM_CROP_TRANSFORM_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_values import _selected_bool, _selected_int
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import (
    JSON_STRING_DEFAULT_METADATA_KEY,
)
from albumentationsx_plugin.hosts.fiftyone.parameter_policy import (
    executable_parameter_fields,
)


def _annotation_field_default(field: AnnotationField, params: Mapping[str, object]) -> bool:
    raw_selected_fields = params.get(SELECTED_LABEL_FIELDS_PARAM_NAME)
    if isinstance(raw_selected_fields, list | tuple):
        return field.name in {str(field_name) for field_name in raw_selected_fields}

    if not annotation_field_selection_is_explicit(params):
        return True

    raw_value = params.get(annotation_field_param_name(field.name), True)
    return raw_value is True


def _annotation_field_caption(field: AnnotationField) -> str:
    if field.albu_target is None:
        return "Classification labels are copied."
    if field.label_type == FIELD_TYPE_HEATMAP:
        return (
            "Heatmap labels use image targets for geometry-only synchronization; "
            "mixed color/intensity stages are blocked."
        )
    return f"{field.label_type.capitalize()} labels use {field.albu_target} targets."


def _selected_transform_name(
    raw_value: object,
    *,
    supported_transform_names: tuple[str, ...],
    step_number: int,
) -> str:
    if isinstance(raw_value, str) and raw_value in supported_transform_names:
        return raw_value
    default_for_step = _default_transform_name_for_step(step_number, supported_transform_names)
    if default_for_step is not None:
        return default_for_step
    if DEFAULT_DYNAMIC_TRANSFORM_NAME in supported_transform_names:
        return DEFAULT_DYNAMIC_TRANSFORM_NAME
    try:
        return supported_transform_names[0]
    except IndexError as error:
        raise UnsupportedTransformError(
            DEFAULT_DYNAMIC_TRANSFORM_NAME,
            message="No supported transforms are available for the augment form.",
            context={"reason_code": "empty_catalog"},
        ) from error


def _default_transform_name_for_step(
    step_number: int,
    supported_transform_names: tuple[str, ...],
) -> str | None:
    try:
        candidate = FIXED_TRANSFORM_NAMES[step_number - 1]
    except IndexError:
        candidate = DEFAULT_DYNAMIC_TRANSFORM_NAME
    return candidate if candidate in supported_transform_names else None


def _executable_ui_fields(
    *,
    selected_transform_name: str,
    catalog_provider: TransformCatalogProvider,
    parameter_fields: tuple[FormFieldSchema, ...],
    params: Mapping[str, object],
    step_number: int,
    random_crop_defaults: RandomCropDefaults | None,
) -> tuple[FormFieldSchema, ...]:
    fields: list[FormFieldSchema] = []
    for schema_field in executable_parameter_fields(
        selected_transform_name=selected_transform_name,
        catalog_provider=catalog_provider,
        parameter_fields=parameter_fields,
    ):
        ui_field = _executable_ui_field(
            selected_transform_name=selected_transform_name,
            field=schema_field,
            random_crop_defaults=random_crop_defaults,
        )
        compact_field = replace(ui_field, help_text=_compact_help_text(ui_field.help_text))
        fields.append(_with_current_default(compact_field, params=params, step_number=step_number))
    return tuple(fields)


def _pipeline_stage_control_fields(
    *,
    params: Mapping[str, object],
    step_number: int,
) -> tuple[FormFieldSchema, FormFieldSchema]:
    return (
        FormFieldSchema(
            name=pipeline_stage_enabled_field_name(step_number),
            kind=FieldKind.BOOLEAN,
            label=PIPELINE_STAGE_ENABLED_LABEL,
            required=False,
            default=_selected_bool(
                params.get(pipeline_stage_enabled_field_name(step_number)),
                default=True,
            ),
            help_text="Skip this stage without clearing its transform settings.",
        ),
        FormFieldSchema(
            name=pipeline_stage_order_field_name(step_number),
            kind=FieldKind.INTEGER,
            label=PIPELINE_STAGE_ORDER_LABEL,
            required=False,
            default=_selected_int(
                params.get(pipeline_stage_order_field_name(step_number)),
                default=step_number,
                min_value=1,
                max_value=MAX_PIPELINE_STEPS,
            ),
            min_value=1,
            max_value=MAX_PIPELINE_STEPS,
            help_text="Lower values run earlier. Each enabled stage must have a different order.",
        ),
    )


def _with_current_default(
    field: FormFieldSchema,
    *,
    params: Mapping[str, object],
    step_number: int,
) -> FormFieldSchema:
    parameter_name = pipeline_step_field_name(step_number, field.name)
    if parameter_name not in params:
        return field
    if field.kind is FieldKind.JSON and isinstance(params[parameter_name], str):
        return replace(
            field,
            required=False,
            default=None,
            metadata={**field.metadata, JSON_STRING_DEFAULT_METADATA_KEY: params[parameter_name]},
        )
    return replace(field, required=False, default=normalize_json_value(params[parameter_name]))


def _executable_ui_field(
    *,
    selected_transform_name: str,
    field: FormFieldSchema,
    random_crop_defaults: RandomCropDefaults | None,
) -> FormFieldSchema:
    if selected_transform_name == RANDOM_CROP_TRANSFORM_NAME:
        return _random_crop_ui_field(field, random_crop_defaults=random_crop_defaults)
    return field


def _random_crop_ui_field(
    field: FormFieldSchema,
    *,
    random_crop_defaults: RandomCropDefaults | None,
) -> FormFieldSchema:
    if field.name not in {"height", "width"}:
        return field

    default = _random_crop_field_default(field.name, random_crop_defaults)
    return replace(
        field,
        required=False,
        default=default,
        help_text=_field_help_text(field, random_crop_defaults),
    )


def _random_crop_field_default(field_name: str, random_crop_defaults: RandomCropDefaults | None) -> int:
    if random_crop_defaults is None:
        return DEFAULT_CROP_SIZE
    if field_name == "height":
        return random_crop_defaults.height
    return random_crop_defaults.width


def _field_help_text(field: FormFieldSchema, random_crop_defaults: RandomCropDefaults | None) -> str | None:
    if random_crop_defaults is None:
        return field.help_text
    return random_crop_defaults.help_text


def _compact_help_text(help_text: str | None) -> str | None:
    if help_text is None:
        return None

    summary = help_text.split("\n-", maxsplit=1)[0]
    summary = summary.split('\n"', maxsplit=1)[0]
    summary = summary.split("Default:", maxsplit=1)[0]
    summary = " ".join(summary.split()).strip().rstrip(":")
    for separator in (". ", "? ", "! "):
        if separator in summary:
            summary = summary.split(separator, maxsplit=1)[0] + separator[0]
            break
    if summary.startswith("Whether to use "):
        summary = "Use " + summary.removeprefix("Whether to use ")
    if summary:
        summary = summary[0].upper() + summary[1:]
    return summary or None


def _step_parameter_fields(
    *,
    parameter_fields: tuple[FormFieldSchema, ...],
    step_number: int,
) -> tuple[FormFieldSchema, ...]:
    return tuple(
        replace(
            field,
            name=pipeline_step_field_name(step_number, field.name),
            label=_parameter_label(field),
        )
        for field in parameter_fields
    )


def _parameter_label(field: FormFieldSchema) -> str:
    if field.name == PROBABILITY_FIELD_NAME:
        return "Probability"
    return field.label or field.name
