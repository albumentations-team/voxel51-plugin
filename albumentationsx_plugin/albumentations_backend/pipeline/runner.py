"""AlbumentationsX image pipeline runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias, cast

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
    targets: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlbumentationsImagePipelineRunner:
    """Small wrapper around `ReplayCompose` for image-only execution."""

    config: PipelineConfig
    transforms: tuple[A.BasicTransform, ...]

    def apply(
        self,
        image: object,
        *,
        targets: Mapping[str, object] | None = None,
    ) -> AlbumentationsImagePipelineResult:
        """Apply the configured pipeline to one RGB image array."""

        transform_name = _pipeline_name(self.config)
        source_image = validate_rgb_array(image, transform_name=transform_name)
        target_values = dict(targets or {})
        compose = A.ReplayCompose(
            list(self.transforms),
            bbox_params=_bbox_params(target_values),
            keypoint_params=_keypoint_params(target_values),
            seed=self.config.seed,
        )
        try:
            output = cast(Mapping[str, Any], compose(image=source_image, **cast(dict[str, Any], target_values)))
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
            targets=_output_targets(output, target_values),
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


def _bbox_params(targets: Mapping[str, object]) -> A.BboxParams | None:
    if "bboxes" not in targets:
        return None
    return A.BboxParams(
        coord_format="pascal_voc",
        label_fields=("bbox_indices",),
        filter_invalid_bboxes=True,
        clip_bboxes_on_input=True,
    )


def _keypoint_params(targets: Mapping[str, object]) -> A.KeypointParams | None:
    if "keypoints" not in targets:
        return None
    return A.KeypointParams(
        coord_format="xy",
        label_fields=("keypoint_indices",),
        remove_invisible=True,
        label_mapping={},
    )


def _output_targets(output: Mapping[str, Any], input_targets: Mapping[str, object]) -> dict[str, object]:
    return {name: output[name] for name in input_targets if name in output}


def _shape_context(image: np.ndarray) -> list[int]:
    return [int(part) for part in image.shape]
