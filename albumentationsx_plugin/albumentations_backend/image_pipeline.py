"""Reusable catalog-backed runtime and per-image dimension validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.albumentations_backend.pipeline import (
    AlbumentationsImagePipelineRunner,
    AlbumentationsPipelineFactory,
    build_default_pipeline_factory,
    validate_rgb_array,
)
from albumentationsx_plugin.core import (
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
    InvalidParameterError,
    PipelineConfig,
    TransformConfig,
)
from albumentationsx_plugin.core.serialization import JSONDict

RGBArray: TypeAlias = npt.NDArray[np.uint8]
_ImageShape: TypeAlias = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class FixedImagePipelineResult:
    """Output of applying the catalog-backed image pipeline to one image."""

    image: RGBArray
    replay: JSONDict
    targets: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class FixedImagePipeline:
    """Validated executable image-only Albumentations pipeline."""

    config: PipelineConfig
    runner: AlbumentationsImagePipelineRunner

    def __post_init__(self) -> None:
        _validate_editor_limits(self.config)

    def apply(
        self,
        image: object,
        *,
        targets: Mapping[str, object] | None = None,
    ) -> FixedImagePipelineResult:
        """Apply the configured transform to one RGB image array."""

        source_image = validate_rgb_array(image, transform_name=self.config.transforms[0].name)
        validate_pipeline_image_shape(self.config, image_shape=source_image.shape)
        result = self.runner.apply(source_image, targets=targets)
        return FixedImagePipelineResult(image=result.image, replay=result.replay, targets=result.targets)


def create_fixed_image_pipeline(config: PipelineConfig) -> FixedImagePipeline:
    """Validate configuration while constructing a reusable image pipeline."""

    _validate_editor_limits(config)
    runner = build_default_pipeline_factory().create_runner(config)
    return FixedImagePipeline(config=config, runner=runner)


def validate_fixed_pipeline_config(
    config: PipelineConfig,
    *,
    image_shape: _ImageShape | None = None,
    factory: AlbumentationsPipelineFactory | None = None,
) -> None:
    """Validate a pipeline config against the catalog and editor limits."""

    _validate_editor_limits(config)
    (factory or build_default_pipeline_factory()).validate(config)
    validate_pipeline_image_shape(config, image_shape=image_shape)


def _validate_editor_limits(config: PipelineConfig) -> None:
    if not config.transforms:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="transforms",
            message="The pipeline editor requires at least one enabled transform.",
            context={"transform_count": len(config.transforms)},
        )
    if len(config.transforms) > MAX_PIPELINE_STEPS:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="transforms",
            message=f"The pipeline editor supports at most {MAX_PIPELINE_STEPS} transforms.",
            context={"transform_count": len(config.transforms), "max_value": MAX_PIPELINE_STEPS},
        )
    if config.outputs_per_sample > MAX_OUTPUTS_PER_SAMPLE:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="outputs_per_sample",
            message=f"outputs_per_sample must be less than or equal to {MAX_OUTPUTS_PER_SAMPLE}.",
            context={"value": config.outputs_per_sample, "max_value": MAX_OUTPUTS_PER_SAMPLE},
        )


def validate_pipeline_image_shape(config: PipelineConfig, *, image_shape: _ImageShape | None) -> None:
    """Check known dimensions in execution order, without sampling transforms.

    Unknown geometry ends static inference. Dry run still executes the entire
    pipeline in memory, including those stages and their annotation targets.
    """
    shape = image_shape
    for index, transform in enumerate(config.transforms, start=1):
        probability = transform.params.get("p", 1.0)
        if probability == 0:
            continue
        try:
            _validate_image_shape_constraints(transform, image_shape=shape)
        except InvalidParameterError as error:
            raise InvalidParameterError(
                transform_name=transform.name,
                parameter_name=str(error.context["parameter_name"]),
                message=f"Execution stage {index} ({transform.name}): {error.message}",
                context={**error.context, "execution_stage": index},
            ) from error
        if transform.name in {"RandomCrop", "Resize"}:
            height = _positive_int_config_param(transform, "height")
            width = _positive_int_config_param(transform, "width")
            if probability == 1:
                shape = (height, width, 3)
            elif shape is not None:
                shape = (min(shape[0], height), min(shape[1], width), 3)
        elif transform.name not in {"HorizontalFlip", "VerticalFlip", "RandomBrightnessContrast", "NoOp"}:
            shape = None


def _validate_image_shape_constraints(transform: TransformConfig, *, image_shape: _ImageShape | None = None) -> None:
    if transform.name != "RandomCrop" or image_shape is None or transform.params.get("pad_if_needed") is True:
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
        message=f"{parameter_name}={value} exceeds the image dimension {image_value}. Reduce {parameter_name} to {image_value} or less, or resize before this crop.",
        context={"value": value, "image_value": image_value},
    )
