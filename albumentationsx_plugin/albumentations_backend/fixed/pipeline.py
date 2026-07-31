"""Small fixed Albumentations pipeline for the first executable MVP slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

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
    InvalidParameterError,
    PipelineConfig,
    TransformConfig,
    UnsupportedTransformError,
)
from albumentationsx_plugin.core.serialization import JSONDict

RGBArray: TypeAlias = npt.NDArray[np.uint8]
_ImageShape: TypeAlias = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class FixedImagePipelineResult:
    """Output of applying the temporary fixed transform pipeline to one image."""

    image: RGBArray
    replay: JSONDict


@dataclass(frozen=True, slots=True)
class FixedImagePipeline:
    """Validated executable image-only Albumentations pipeline."""

    config: PipelineConfig
    runner: AlbumentationsImagePipelineRunner

    def __post_init__(self) -> None:
        validate_fixed_pipeline_config(self.config)

    def apply(self, image: object) -> FixedImagePipelineResult:
        """Apply the configured transform to one RGB image array."""

        source_image = validate_rgb_array(image, transform_name=self.config.transforms[0].name)
        validate_fixed_pipeline_config(self.config, image_shape=source_image.shape)
        result = self.runner.apply(source_image)
        return FixedImagePipelineResult(image=result.image, replay=result.replay)


def build_fixed_pipeline_config(params: Mapping[str, object]) -> PipelineConfig:
    """Create the fixed-slice pipeline config from FiftyOne operator params."""

    transform_name = _str_param(params, "transform", default=FIXED_TRANSFORM_NAMES[0])
    outputs_per_sample = _int_param(
        params,
        "outputs_per_sample",
        default=1,
        min_value=1,
        max_value=MAX_OUTPUTS_PER_SAMPLE,
        transform_name=transform_name,
    )
    probability = _float_param(
        params,
        "p",
        default=DEFAULT_TRANSFORM_PROBABILITY,
        min_value=0.0,
        max_value=1.0,
        transform_name=transform_name,
    )

    transform_params: dict[str, object] = {"p": probability}
    match transform_name:
        case "HorizontalFlip":
            pass
        case "RandomBrightnessContrast":
            transform_params["brightness_range"] = _range_param(
                params,
                "brightness_range",
                default_lower=DEFAULT_BRIGHTNESS_RANGE[0],
                default_upper=DEFAULT_BRIGHTNESS_RANGE[1],
                transform_name=transform_name,
            )
            transform_params["contrast_range"] = _range_param(
                params,
                "contrast_range",
                default_lower=DEFAULT_CONTRAST_RANGE[0],
                default_upper=DEFAULT_CONTRAST_RANGE[1],
                transform_name=transform_name,
            )
        case "RandomCrop":
            transform_params["height"] = _int_param(
                params,
                "height",
                default=DEFAULT_CROP_SIZE,
                min_value=1,
                max_value=None,
                transform_name=transform_name,
                aliases=("crop_height",),
            )
            transform_params["width"] = _int_param(
                params,
                "width",
                default=DEFAULT_CROP_SIZE,
                min_value=1,
                max_value=None,
                transform_name=transform_name,
                aliases=("crop_width",),
            )
        case _:
            raise UnsupportedTransformError(
                transform_name,
                context={"supported_transforms": list(FIXED_TRANSFORM_NAMES)},
            )

    config = PipelineConfig(
        transforms=(TransformConfig(name=transform_name, params=transform_params),),
        outputs_per_sample=outputs_per_sample,
        use_replay=True,
        options={"source": "fixed_mvp_slice"},
    )
    validate_fixed_pipeline_config(config)
    return config


def create_fixed_image_pipeline(config: PipelineConfig) -> FixedImagePipeline:
    """Validate and create the fixed image pipeline."""

    validate_fixed_pipeline_config(config)
    runner = build_default_pipeline_factory().create_runner(config)
    return FixedImagePipeline(config=config, runner=runner)


def validate_fixed_pipeline_config(config: PipelineConfig, *, image_shape: _ImageShape | None = None) -> None:
    """Validate a pipeline config against the temporary fixed transform set."""

    if len(config.transforms) != 1:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="transforms",
            message="The fixed MVP slice supports exactly one transform.",
            context={"transform_count": len(config.transforms)},
        )
    if config.outputs_per_sample > MAX_OUTPUTS_PER_SAMPLE:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="outputs_per_sample",
            message=f"outputs_per_sample must be less than or equal to {MAX_OUTPUTS_PER_SAMPLE}.",
            context={"value": config.outputs_per_sample, "max_value": MAX_OUTPUTS_PER_SAMPLE},
        )

    transform = config.transforms[0]
    if transform.name not in FIXED_TRANSFORM_NAMES:
        raise UnsupportedTransformError(
            transform.name,
            context={"supported_transforms": list(FIXED_TRANSFORM_NAMES)},
        )

    _validate_probability(transform)
    match transform.name:
        case "HorizontalFlip":
            _reject_unknown_params(transform, allowed={"p"})
        case "RandomBrightnessContrast":
            _reject_unknown_params(transform, allowed={"p", "brightness_range", "contrast_range"})
            _range_config_param(
                transform,
                "brightness_range",
                default_lower=DEFAULT_BRIGHTNESS_RANGE[0],
                default_upper=DEFAULT_BRIGHTNESS_RANGE[1],
            )
            _range_config_param(
                transform,
                "contrast_range",
                default_lower=DEFAULT_CONTRAST_RANGE[0],
                default_upper=DEFAULT_CONTRAST_RANGE[1],
            )
        case "RandomCrop":
            _reject_unknown_params(transform, allowed={"p", "height", "width"})
            height = _positive_int_config_param(transform, "height")
            width = _positive_int_config_param(transform, "width")
            if image_shape is not None:
                image_height, image_width, _channels = image_shape
                if height > image_height:
                    _raise_crop_size_error(transform, "height", value=height, image_value=image_height)
                if width > image_width:
                    _raise_crop_size_error(transform, "width", value=width, image_value=image_width)


def _validate_probability(transform: TransformConfig) -> float:
    raw_probability = transform.params.get("p", DEFAULT_TRANSFORM_PROBABILITY)
    if not isinstance(raw_probability, int | float) or isinstance(raw_probability, bool):
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name="p",
            message="p must be a number between 0 and 1.",
            context={"value": raw_probability},
        )
    probability = float(raw_probability)
    if probability < 0.0 or probability > 1.0:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name="p",
            message="p must be a number between 0 and 1.",
            context={"value": probability},
        )
    return probability


def _reject_unknown_params(transform: TransformConfig, *, allowed: set[str]) -> None:
    unknown = sorted(set(transform.params) - allowed)
    if unknown:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=unknown[0],
            message=f"{transform.name} received unsupported fixed-slice parameters.",
            context={"unknown_parameters": unknown, "allowed_parameters": sorted(allowed)},
        )


def _range_config_param(
    transform: TransformConfig,
    parameter_name: str,
    *,
    default_lower: float,
    default_upper: float,
) -> tuple[float, float]:
    raw_range = transform.params.get(parameter_name, [default_lower, default_upper])
    if not isinstance(raw_range, list | tuple) or len(raw_range) != 2:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a two-value numeric range.",
            context={"value": raw_range},
        )

    lower = _numeric_config_param(transform, parameter_name, raw_range[0])
    upper = _numeric_config_param(transform, parameter_name, raw_range[1])
    if lower < -1.0 or upper > 1.0:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} values must be between -1.0 and 1.0.",
            context={"value": [lower, upper], "min_value": -1.0, "max_value": 1.0},
        )
    if lower > upper:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} lower bound must be less than or equal to the upper bound.",
            context={"value": [lower, upper]},
        )
    return lower, upper


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


def _numeric_config_param(transform: TransformConfig, parameter_name: str, value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must contain only numbers.",
            context={"value": value},
        )
    return float(value)


def _range_param(
    params: Mapping[str, object],
    parameter_prefix: str,
    *,
    default_lower: float,
    default_upper: float,
    transform_name: str,
) -> list[float]:
    direct_value = params.get(parameter_prefix)
    if direct_value is not None:
        return _direct_range_param(
            direct_value,
            parameter_prefix=parameter_prefix,
            transform_name=transform_name,
        )

    lower = _float_param(
        params,
        f"{parameter_prefix}_min",
        default=default_lower,
        min_value=-1.0,
        max_value=1.0,
        transform_name=transform_name,
    )
    upper = _float_param(
        params,
        f"{parameter_prefix}_max",
        default=default_upper,
        min_value=-1.0,
        max_value=1.0,
        transform_name=transform_name,
    )
    if lower > upper:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_prefix,
            message=f"{parameter_prefix}_min must be less than or equal to {parameter_prefix}_max.",
            context={"value": [lower, upper]},
        )
    return [lower, upper]


def _direct_range_param(value: object, *, parameter_prefix: str, transform_name: str) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_prefix,
            message=f"{parameter_prefix} must be a two-value numeric range.",
            context={"value": value},
        )
    lower = _numeric_config_param(TransformConfig(name=transform_name), parameter_prefix, value[0])
    upper = _numeric_config_param(TransformConfig(name=transform_name), parameter_prefix, value[1])
    if lower < -1.0 or upper > 1.0:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_prefix,
            message=f"{parameter_prefix} values must be between -1.0 and 1.0.",
            context={"value": [lower, upper], "min_value": -1.0, "max_value": 1.0},
        )
    if lower > upper:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_prefix,
            message=f"{parameter_prefix} lower bound must be less than or equal to the upper bound.",
            context={"value": [lower, upper]},
        )
    return [lower, upper]


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


def _float_param(
    params: Mapping[str, object],
    parameter_name: str,
    *,
    default: float,
    min_value: float,
    max_value: float,
    transform_name: str,
) -> float:
    raw_value = params.get(parameter_name, default)
    if not isinstance(raw_value, int | float) or isinstance(raw_value, bool):
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a number.",
            context={"value": raw_value},
        )
    value = float(raw_value)
    if value < min_value or value > max_value:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name=parameter_name,
            message=f"{parameter_name} must be between {min_value} and {max_value}.",
            context={"value": value, "min_value": min_value, "max_value": max_value},
        )
    return value


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
