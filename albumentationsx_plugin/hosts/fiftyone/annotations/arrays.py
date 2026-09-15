"""Load, validate and project annotation masks and heatmaps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import fiftyone as fo
import numpy as np
import numpy.typing as npt
from PIL import Image

from albumentationsx_plugin.core import JSONValue, MediaIOError
from albumentationsx_plugin.hosts.fiftyone.annotations.geometry import _bbox_pixel_slice, _relative_bbox
from albumentationsx_plugin.hosts.fiftyone.annotations.payload_values import _shape_context
from albumentationsx_plugin.hosts.fiftyone.annotations.target_types import (
    _HEATMAP_MAP_FIELD,
    _HEATMAP_MAP_PATH_FIELD,
    _MASK_FIELD,
    _SEGMENTATION_MASK_PATH_FIELD,
    _AnnotationRef,
)


def _heatmap_payload_array(payload: Mapping[str, object]) -> npt.NDArray[np.float32] | None:
    value = payload.get(_HEATMAP_MAP_FIELD)
    if value is None:
        return None
    return _heatmap_output_array(value)


def _heatmap_target_array(payload: Mapping[str, object]) -> npt.NDArray[np.float32] | None:
    heatmap = _heatmap_payload_array(payload)
    if heatmap is None:
        return None
    return heatmap[:, :, np.newaxis]


def _heatmap_output_array(value: object) -> npt.NDArray[np.float32]:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]
    if array.ndim != 2:
        raise MediaIOError(
            filepath="<memory>",
            message="FiftyOne heatmap must be a 2D array.",
            context={"reason": "invalid_heatmap_shape", "shape": _shape_context(array)},
        )
    if array.shape[0] <= 0 or array.shape[1] <= 0:
        raise MediaIOError(
            filepath="<memory>",
            message="FiftyOne heatmap must have positive width and height.",
            context={"reason": "invalid_heatmap_shape", "shape": _shape_context(array)},
        )
    return array


def _mask_array(payload: Mapping[str, object]) -> npt.NDArray[Any] | None:
    value = payload.get(_MASK_FIELD)
    if value is None:
        return None
    return np.asarray(value)


def _has_mask(label: fo.Detection | fo.Segmentation) -> bool:
    value = label.has_mask
    return bool(value() if callable(value) else value)


def _has_heatmap(label: fo.Heatmap) -> bool:
    value = label.has_map
    return bool(value() if callable(value) else value)


def _heatmap_map(label: fo.Heatmap) -> npt.NDArray[np.float32]:
    try:
        return _heatmap_output_array(label.get_map())
    except (OSError, TypeError, ValueError) as error:
        raise MediaIOError(
            filepath=_heatmap_map_path(label) or "<memory>",
            message="FiftyOne heatmap could not be read.",
            context={
                "reason": "unreadable_heatmap",
                "exception_type": type(error).__name__,
            },
        ) from error


def _heatmap_map_path(label: fo.Heatmap) -> str | None:
    value = getattr(label, _HEATMAP_MAP_PATH_FIELD, None)
    return value if isinstance(value, str) and value.strip() else None


def _detection_mask(label: fo.Detection) -> npt.NDArray[Any] | None:
    if not _has_mask(label):
        return None
    try:
        mask = label.get_mask()
    except (OSError, TypeError, ValueError) as error:
        raise MediaIOError(
            filepath=_detection_mask_path(label) or "<memory>",
            message="FiftyOne detection instance mask could not be read.",
            context={
                "reason": "unreadable_detection_mask",
                "exception_type": type(error).__name__,
            },
        ) from error
    return None if mask is None else np.asarray(mask)


def _detection_mask_path(label: fo.Detection) -> str | None:
    value = getattr(label, _SEGMENTATION_MASK_PATH_FIELD, None)
    return value if isinstance(value, str) and value.strip() else None


def _segmentation_mask(label: fo.Segmentation) -> npt.NDArray[Any]:
    try:
        return np.asarray(label.get_mask())
    except (OSError, TypeError, ValueError) as error:
        raise MediaIOError(
            filepath=_segmentation_mask_path(label) or "<memory>",
            message="FiftyOne segmentation mask could not be read.",
            context={
                "reason": "unreadable_segmentation_mask",
                "exception_type": type(error).__name__,
            },
        ) from error


def _segmentation_mask_path(label: fo.Segmentation) -> str | None:
    value = getattr(label, _SEGMENTATION_MASK_PATH_FIELD, None)
    return value if isinstance(value, str) and value.strip() else None


def _full_image_detection_mask(
    detection: Mapping[str, object],
    bbox: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> npt.NDArray[np.uint8] | None:
    local_mask = _mask_array(detection)
    if local_mask is None:
        return None

    target_slice = _bbox_pixel_slice(bbox, image_width=image_width, image_height=image_height)
    if target_slice is None:
        return None

    x_min, y_min, x_max, y_max = target_slice
    resized_mask = _resize_instance_mask(
        _instance_mask_array(local_mask),
        height=y_max - y_min,
        width=x_max - x_min,
    )
    full_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    full_mask[y_min:y_max, x_min:x_max] = resized_mask
    return full_mask


def _output_detection_mask(
    ref: _AnnotationRef,
    detection: Mapping[str, object],
    output_masks_by_ref: Mapping[_AnnotationRef, npt.NDArray[Any]],
    *,
    image_width: int,
    image_height: int,
) -> npt.NDArray[np.uint8] | None:
    full_mask = output_masks_by_ref.get(ref)
    if full_mask is None:
        return None

    bbox = _relative_bbox(detection)
    if bbox is None:
        return None

    target_slice = _bbox_pixel_slice(bbox, image_width=image_width, image_height=image_height)
    if target_slice is None:
        return None

    x_min, y_min, x_max, y_max = target_slice
    local_mask = _instance_mask_array(full_mask)[y_min:y_max, x_min:x_max]
    if not np.any(local_mask):
        return None
    return local_mask


def _instance_mask_array(mask: object) -> npt.NDArray[np.uint8]:
    array = np.asarray(mask)
    if array.ndim > 2:
        array = array[:, :, 0]
    if array.ndim != 2:
        raise MediaIOError(
            filepath="<memory>",
            message="FiftyOne detection instance mask must be a 2D array.",
            context={"reason": "invalid_detection_mask_shape", "shape": _shape_context(array)},
        )
    if array.shape[0] <= 0 or array.shape[1] <= 0:
        raise MediaIOError(
            filepath="<memory>",
            message="FiftyOne detection instance mask must have positive width and height.",
            context={"reason": "invalid_detection_mask_shape", "shape": _shape_context(array)},
        )
    return np.asarray(array > 0, dtype=np.uint8)


def _resize_instance_mask(
    mask: npt.NDArray[np.uint8],
    *,
    height: int,
    width: int,
) -> npt.NDArray[np.uint8]:
    if mask.shape == (height, width):
        return mask

    resized = Image.fromarray(mask).resize((width, height), resample=Image.Resampling.NEAREST)
    return np.asarray(resized, dtype=np.uint8)


def _mask_to_json(mask: object) -> list[JSONValue]:
    return cast(list[JSONValue], np.asarray(mask).tolist())


def _heatmap_to_json(heatmap: object) -> list[JSONValue]:
    return cast(list[JSONValue], np.asarray(heatmap, dtype=np.float32).tolist())
