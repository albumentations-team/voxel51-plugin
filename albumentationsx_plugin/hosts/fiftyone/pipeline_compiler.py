"""Compile FiftyOne stage slots and form values into neutral pipeline configs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.image_pipeline import validate_fixed_pipeline_config
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.albumentations_backend.pipeline.coercion import coerce_transform_params
from albumentationsx_plugin.albumentations_backend.pipeline.factory import AlbumentationsPipelineFactory
from albumentationsx_plugin.albumentations_backend.pipeline.registry import AlbumentationsTransformRegistry
from albumentationsx_plugin.core import (
    FIXED_TRANSFORM_NAMES,
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    FieldKind,
    FormFieldSchema,
    InvalidParameterError,
    ParameterSchemaProvider,
    PipelineConfig,
    TransformCatalogProvider,
    TransformConfig,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.parameter_policy import (
    executable_parameter_fields,
    is_json_fallback_parameter,
)

_MISSING: Final[object] = object()


@dataclass(frozen=True, slots=True)
class _PipelineStageSelection:
    step_number: int
    execution_order: int


def build_fixed_pipeline_config(
    params: Mapping[str, object],
    *,
    catalog_provider: TransformCatalogProvider | None = None,
    parameter_schema_provider: ParameterSchemaProvider | None = None,
) -> PipelineConfig:
    """Create the catalog-backed pipeline config from FiftyOne operator params."""

    catalog_provider = catalog_provider or AlbuSpecCatalogProvider()
    parameter_schema_provider = parameter_schema_provider or AlbuSpecParameterSchemaProvider(
        catalog_provider=catalog_provider,
    )

    outputs_per_sample = _int_param(
        params,
        "outputs_per_sample",
        default=1,
        min_value=1,
        max_value=MAX_OUTPUTS_PER_SAMPLE,
        transform_name="<pipeline>",
    )
    stage_selections = _selected_pipeline_stages(params)
    transforms = []
    for stage in stage_selections:
        try:
            transforms.append(
                _step_transform_config(
                    params,
                    stage.step_number,
                    catalog_provider=catalog_provider,
                    parameter_schema_provider=parameter_schema_provider,
                )
            )
        except InvalidParameterError as error:
            raise InvalidParameterError(
                transform_name=str(error.context.get("transform_name", "<pipeline>")),
                parameter_name=str(error.context.get("parameter_name", "transform")),
                message=f"Stage {stage.step_number}: {error.message}",
                context={**error.context, "stage_number": stage.step_number},
            ) from error

    config = PipelineConfig(
        transforms=tuple(transforms),
        outputs_per_sample=outputs_per_sample,
        use_replay=True,
        options={"source": "catalog_mvp_pipeline"},
    )
    validate_fixed_pipeline_config(
        config,
        factory=AlbumentationsPipelineFactory(
            registry=AlbumentationsTransformRegistry(catalog_provider),
            parameter_schema_provider=parameter_schema_provider,
        ),
    )
    return config


def _step_transform_config(
    params: Mapping[str, object],
    step_number: int,
    *,
    catalog_provider: TransformCatalogProvider,
    parameter_schema_provider: ParameterSchemaProvider,
) -> TransformConfig:
    transform_name = _str_param(
        params,
        pipeline_step_field_name(step_number, "transform"),
        default=_default_transform_name(step_number),
    )
    parameter_schema = parameter_schema_provider.get_parameter_schema(transform_name)
    parameter_fields = executable_parameter_fields(
        selected_transform_name=transform_name,
        catalog_provider=catalog_provider,
        parameter_fields=parameter_schema,
    )
    transform = TransformConfig(
        name=transform_name,
        params=_step_transform_params(
            params,
            transform_name=transform_name,
            parameter_fields=parameter_fields,
            step_number=step_number,
        ),
    )
    return TransformConfig(
        name=transform_name,
        params=coerce_transform_params(transform, _coercion_parameter_fields(parameter_fields)),
    )


def _coercion_parameter_fields(parameter_fields: tuple[FormFieldSchema, ...]) -> tuple[FormFieldSchema, ...]:
    return tuple(
        replace(field, default=None) if is_json_fallback_parameter(field) else field for field in parameter_fields
    )


def _step_transform_params(
    params: Mapping[str, object],
    *,
    transform_name: str,
    parameter_fields: tuple[FormFieldSchema, ...],
    step_number: int,
) -> dict[str, object]:
    transform_params: dict[str, object] = {}
    for field in parameter_fields:
        value = _step_parameter_value(params, field, step_number=step_number)
        if value is _MISSING:
            if is_json_fallback_parameter(field):
                continue
            value = _default_parameter_value(field)
        if value is not _MISSING:
            transform_params[field.name] = value
    return transform_params


def _step_parameter_value(
    params: Mapping[str, object],
    field: FormFieldSchema,
    *,
    step_number: int,
) -> object:
    parameter_name = pipeline_step_field_name(step_number, field.name)
    aliases = _legacy_parameter_aliases(step_number, field.name)
    if field.kind == FieldKind.NUMBER_RANGE:
        return _number_range_param_value(params, parameter_name, field=field, aliases=aliases)
    if field.kind == FieldKind.JSON:
        value = _optional_param_value(params, parameter_name, aliases=aliases, default=_MISSING)
        if isinstance(value, str) and not value.strip() and not field.required:
            return _MISSING
        return value
    return _optional_param_value(params, parameter_name, aliases=aliases, default=_MISSING)


def _number_range_param_value(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    field: FormFieldSchema,
    aliases: tuple[str, ...],
) -> object:
    direct_value = _optional_param_value(params, parameter_name, aliases=aliases, default=_MISSING)
    if direct_value is not _MISSING:
        return direct_value

    lower = _optional_param_value(
        params,
        f"{parameter_name}_min",
        aliases=tuple(f"{alias}_min" for alias in aliases),
        default=_MISSING,
    )
    upper = _optional_param_value(
        params,
        f"{parameter_name}_max",
        aliases=tuple(f"{alias}_max" for alias in aliases),
        default=_MISSING,
    )
    if lower is _MISSING and upper is _MISSING:
        return _MISSING

    default_lower, default_upper = _range_default_values(field)
    return [
        default_lower if lower is _MISSING else lower,
        default_upper if upper is _MISSING else upper,
    ]


def _range_default_values(field: FormFieldSchema) -> tuple[object, object]:
    default = field.default
    if isinstance(default, list | tuple) and len(default) == 2:
        return default[0], default[1]
    return None, None


def _default_parameter_value(field: FormFieldSchema) -> object:
    return _MISSING if field.default is None else field.default


def _selected_pipeline_stages(params: Mapping[str, object]) -> tuple[_PipelineStageSelection, ...]:
    visible_step_count = _pipeline_step_count(params)
    selections: list[_PipelineStageSelection] = []
    for step_number in range(1, visible_step_count + 1):
        enabled = _bool_param(
            params,
            pipeline_stage_enabled_field_name(step_number),
            default=True,
            transform_name="<pipeline>",
        )
        if not enabled:
            continue
        selections.append(
            _PipelineStageSelection(
                step_number=step_number,
                execution_order=_int_param(
                    params,
                    pipeline_stage_order_field_name(step_number),
                    default=step_number,
                    min_value=1,
                    max_value=MAX_PIPELINE_STEPS,
                    transform_name="<pipeline>",
                ),
            )
        )

    if not selections:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="pipeline_stages",
            message="At least one pipeline stage must be enabled.",
            context={"visible_step_count": visible_step_count},
        )
    return tuple(sorted(selections, key=lambda stage: (stage.execution_order, stage.step_number)))


def _pipeline_step_count(params: Mapping[str, object]) -> int:
    return _int_param(
        params,
        PIPELINE_STEP_COUNT_FIELD_NAME,
        default=1,
        min_value=1,
        max_value=MAX_PIPELINE_STEPS,
        transform_name="<pipeline>",
    )


def _default_transform_name(step_number: int) -> str:
    try:
        return FIXED_TRANSFORM_NAMES[step_number - 1]
    except IndexError:
        return FIXED_TRANSFORM_NAMES[0]


def _legacy_parameter_aliases(step_number: int, parameter_name: str) -> tuple[str, ...]:
    if step_number != 1:
        return ()
    match parameter_name:
        case "height":
            return ("crop_height",)
        case "width":
            return ("crop_width",)
        case _:
            return ()


def _str_param(params: Mapping[str, object], parameter_name: str, *, default: str) -> str:
    raw_value = params.get(parameter_name, default)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise InvalidParameterError(
            transform_name="<operator>",
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a non-empty string.",
            context={"value": raw_value},
        )
    return raw_value


def _int_param(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    default: int,
    min_value: int,
    max_value: int | None,
    transform_name: str,
    aliases: tuple[str, ...] = (),
) -> int:
    raw_value = _param_value(params, parameter_name, default=default, aliases=aliases)
    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be an integer.",
            context={"value": raw_value},
        )
    if raw_value < min_value:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be at least {min_value}.",
            context={"value": raw_value, "min_value": min_value},
        )
    if max_value is not None and raw_value > max_value:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be less than or equal to {max_value}.",
            context={"value": raw_value, "max_value": max_value},
        )
    return raw_value


def _bool_param(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    default: bool,
    transform_name: str,
) -> bool:
    raw_value = _param_value(params, parameter_name, default=default)
    if not isinstance(raw_value, bool):
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a boolean.",
            context={"value": raw_value},
        )
    return raw_value


def _param_value(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    default: object,
    aliases: tuple[str, ...] = (),
) -> object:
    if parameter_name in params:
        return params[parameter_name]
    for alias in aliases:
        if alias in params:
            return params[alias]
    return default


def _optional_param_value(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    aliases: tuple[str, ...] = (),
    default: object = None,
) -> object:
    if parameter_name in params:
        return params[parameter_name]
    for alias in aliases:
        if alias in params:
            return params[alias]
    return default


def operator_params_from_pipeline(pipeline: PipelineConfig) -> dict[str, object]:
    """Convert a persisted pipeline config back into FiftyOne operator params."""

    transforms = pipeline.transforms[:MAX_PIPELINE_STEPS]
    params: dict[str, object] = {
        PIPELINE_STEP_COUNT_FIELD_NAME: len(transforms),
        "outputs_per_sample": pipeline.outputs_per_sample,
    }
    for step_index, transform in enumerate(transforms, start=1):
        params[pipeline_stage_enabled_field_name(step_index)] = True
        params[pipeline_stage_order_field_name(step_index)] = step_index
        params[pipeline_step_field_name(step_index, "transform")] = transform.name
        for parameter_name, value in transform.params.items():
            params[pipeline_step_field_name(step_index, parameter_name)] = value
    return params
