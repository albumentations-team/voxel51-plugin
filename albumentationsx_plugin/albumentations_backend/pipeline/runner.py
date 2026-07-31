"""AlbumentationsX image pipeline runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias, cast

import albumentations as A
import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.albumentations_backend.pipeline.replay import extract_replay
from albumentationsx_plugin.core import InvalidParameterError, JSONDict, PipelineConfig, TransformConfig

RGBArray: TypeAlias = npt.NDArray[np.uint8]
_ImageShape: TypeAlias = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class AlbumentationsImagePipelineResult:
    """Output of applying a catalog-driven AlbumentationsX image pipeline."""

    image: RGBArray
    replay: JSONDict


@dataclass(frozen=True, slots=True)
class AlbumentationsImagePipelineRunner:
    """Small wrapper around `ReplayCompose` for image-only execution."""

    config: PipelineConfig
    transforms: tuple[A.BasicTransform, ...]

    def apply(self, image: object) -> AlbumentationsImagePipelineResult:
        """Apply the configured pipeline to one RGB image array."""

        transform_name = _pipeline_name(self.config)
        source_image = validate_rgb_array(image, transform_name=transform_name)
        compose = A.ReplayCompose(list(self.transforms), seed=self.config.seed)
        try:
            output = compose(image=source_image)
        except Exception as error:
            raise InvalidParameterError(
                transform_name=transform_name,
                parameter_name="<runtime>",
                message="AlbumentationsX rejected the image or sampled parameters.",
                context={
                    "reason_code": "albumentations_runtime_error",
                    "error": str(error),
                },
            ) from error
        output_image = validate_rgb_array(output["image"], transform_name=transform_name)
        return AlbumentationsImagePipelineResult(
            image=output_image,
            replay=extract_replay(cast(Mapping[str, object], output)),
        )


def validate_rgb_array(image: object, *, transform_name: str) -> RGBArray:
    """Validate that an image is an RGB uint8 NumPy array."""

    if not isinstance(image, np.ndarray):
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name="image",
            message="Image data must be a NumPy array.",
            context={"actual_type": type(image).__name__},
        )
    if image.dtype != np.uint8:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name="image",
            message="Image data must use uint8 dtype.",
            context={"dtype": str(image.dtype), "shape": _shape_context(image)},
        )
    if image.ndim != 3 or image.shape[2] != 3:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name="image",
            message="Image data must have shape (height, width, 3).",
            context={"shape": _shape_context(image)},
        )
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise InvalidParameterError(
            transform_name=transform_name,
            parameter_name="image",
            message="Image data must have positive width and height.",
            context={"shape": _shape_context(image)},
        )
    return cast(RGBArray, image)


def _pipeline_name(config: PipelineConfig) -> str:
    if not config.transforms:
        return "<pipeline>"
    if len(config.transforms) == 1:
        return config.transforms[0].name
    return " -> ".join(_transform_name(transform) for transform in config.transforms)


def _transform_name(transform: TransformConfig) -> str:
    return transform.name


def _shape_context(image: np.ndarray) -> list[int]:
    return [int(part) for part in image.shape]
