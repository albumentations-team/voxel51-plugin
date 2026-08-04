"""Small fixed Albumentations pipeline for the first executable MVP slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.albumentations_backend.pipeline import (
    AlbumentationsImagePipelineRunner,
    build_default_pipeline_factory,
    validate_rgb_array,
)
from albumentationsx_plugin.core import (
    DEFAULT_BRIGHTNESS_RANGE,
    DEFAULT_CONTRAST_RANGE,
    DEFAULT_CROP_SIZE,
    DEFAULT_TRANSFORM_PROBABILITY,
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
    pipeline_step_field_name,
)
from albumentationsx_plugin.core.serialization import JSONDict, normalize_json_value

RGBArray: TypeAlias = npt.NDArray[np.uint8]
_ImageShape: TypeAlias = tuple[int, int, int]
_MISSING: Final[object] = object()
SCHEMA_STATUS_JSON_FALLBACK: Final[str] = "json_fallback"


@dataclass(frozen=True, slots=True)
class FixedImagePipelineResult:
    """Output of applying the temporary fixed transform pipeline to one image."""

    image: RGBArray
    replay: JSONDict
    targets: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class FixedImagePipeline:
    """Validated executable image-only Albumentations pipeline."""

    config: PipelineConfig
    runner: AlbumentationsImagePipelineRunner

    def __post_init__(self) -> None:
        validate_fixed_pipeline_config(self.config)

    def apply(
        self,
        image: object,
        *,
        targets: Mapping[str, object] | None = None,
    ) -> FixedImagePipelineResult:
        """Apply the configured transform to one RGB image array."""

        source_image = validate_rgb_array(image, transform_name=self.config.transforms[0].name)
        validate_fixed_pipeline_config(self.config, image_shape=source_image.shape)
        result = self.runner.apply(source_image, targets=targets)
        return FixedImagePipelineResult(image=result.image, replay=result.replay, targets=result.targets)


def build_fixed_pipeline_config(
    params: Mapping[str, object],
    *,
    catalog_provider: TransformCatalogProvider | None = None,
    parameter_schema_provider: ParameterSchemaProvider | None = None,
) -> PipelineConfig:
    """Create the executable MVP pipeline config from FiftyOne operator params."""

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
    step_count = _pipeline_step_count(params)
    transforms = tuple(
        _step_transform_config(
            params,
            step_number,
            parameter_schema_provider=parameter_schema_provider,
        )
        for step_number in range(1, step_count + 1)
    )

    config = PipelineConfig(
        transforms=transforms,
        outputs_per_sample=outputs_per_sample,
        use_replay=True,
        options={"source": "catalog_mvp_pipeline"},
    )
    validate_fixed_pipeline_config(config)
    return config


def create_fixed_image_pipeline(config: PipelineConfig) -> FixedImagePipeline:
    """Validate and create the fixed image pipeline."""

    validate_fixed_pipeline_config(config)
    runner = build_default_pipeline_factory().create_runner(config)
    return FixedImagePipeline(config=config, runner=runner)


def validate_fixed_pipeline_config(config: PipelineConfig, *, image_shape: _ImageShape | None = None) -> None:
    """Validate a pipeline config against the executable MVP transform set."""

    if not config.transforms:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="transforms",
            message="The fixed MVP slice requires at least one transform.",
            context={"transform_count": len(config.transforms)},
        )
    if len(config.transforms) > MAX_PIPELINE_STEPS:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="transforms",
            message=f"The fixed MVP slice supports at most {MAX_PIPELINE_STEPS} transforms.",
            context={"transform_count": len(config.transforms), "max_value": MAX_PIPELINE_STEPS},
        )
    if config.outputs_per_sample > MAX_OUTPUTS_PER_SAMPLE:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="outputs_per_sample",
            message=f"outputs_per_sample must be less than or equal to {MAX_OUTPUTS_PER_SAMPLE}.",
            context={"value": config.outputs_per_sample, "max_value": MAX_OUTPUTS_PER_SAMPLE},
        )

    build_default_pipeline_factory().validate(config)
    for transform in config.transforms:
        _validate_image_shape_constraints(transform, image_shape=image_shape)


def _step_transform_config(
    params: Mapping[str, object],
    step_number: int,
    *,
    parameter_schema_provider: ParameterSchemaProvider,
) -> TransformConfig:
    transform_name = _str_param(
        params,
        pipeline_step_field_name(step_number, "transform"),
        default=_default_transform_name(step_number),
    )
    parameter_schema = parameter_schema_provider.get_parameter_schema(transform_name)
    return TransformConfig(
        name=transform_name,
        params=_step_transform_params(
            params,
            transform_name=transform_name,
            parameter_fields=_executable_parameter_fields(
                selected_transform_name=transform_name,
                parameter_fields=parameter_schema,
            ),
            step_number=step_number,
        ),
    )


def _executable_parameter_fields(
    *,
    selected_transform_name: str,
    parameter_fields: tuple[FormFieldSchema, ...],
) -> tuple[FormFieldSchema, ...]:
    supported_parameter_names = _fixed_slice_parameter_names(selected_transform_name)
    return tuple(
        _executable_parameter_field(selected_transform_name=selected_transform_name, field=field)
        for field in parameter_fields
        if _is_visible_parameter(field)
        if supported_parameter_names is None or field.name in supported_parameter_names
    )


def _fixed_slice_parameter_names(transform_name: str) -> tuple[str, ...] | None:
    match transform_name:
        case "HorizontalFlip":
            return ("p",)
        case "RandomBrightnessContrast":
            return ("brightness_range", "contrast_range", "p")
        case "RandomCrop":
            return ("height", "width", "p")
        case _:
            return None


def _is_visible_parameter(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") != SCHEMA_STATUS_JSON_FALLBACK


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


def _validate_image_shape_constraints(transform: TransformConfig, *, image_shape: _ImageShape | None = None) -> None:
    if transform.name != "RandomCrop" or image_shape is None:
        return

    height = _positive_int_config_param(transform, "height")
    width = _positive_int_config_param(transform, "width")
    image_height, image_width, _channels = image_shape
    if height > image_height:
        _raise_crop_size_error(transform, "height", value=height, image_value=image_height)
    if width > image_width:
        _raise_crop_size_error(transform, "width", value=width, image_value=image_width)


def _positive_int_config_param(transform: TransformConfig, parameter_name: str) -> int:
    raw_value = transform.params.get(parameter_name)
    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a positive integer.",
            context={"value": raw_value},
        )
    if raw_value < 1:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be at least 1.",
            context={"value": raw_value},
        )
    return raw_value


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


def _raise_crop_size_error(
    transform: TransformConfig,
    parameter_name: str,
    *,
    value: int,
    image_value: int,
) -> None:
    raise InvalidParameterError(
        transform_name=transform.name,
        parameter_name=parameter_name,
        message=f"{parameter_name} must be less than or equal to the source image dimension.",
        context={"value": value, "image_value": image_value},
    )
