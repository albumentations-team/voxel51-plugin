"""Coordinate conversion for boxes, points and polylines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import fiftyone as fo
import numpy as np

from albumentationsx_plugin.hosts.fiftyone.annotations.payload_values import (
    _clamp01,
    _float_sequence,
    _optional_bool,
    _payload_sequence,
    _runtime_sequence,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.target_types import _PIXEL_COORD_EPSILON


def _relative_bbox(payload: Mapping[str, object]) -> list[float] | None:
    bbox = _float_sequence(payload.get("bounding_box"))
    if len(bbox) != 4:
        return None
    x, y, width, height = bbox
    if width <= 0.0 or height <= 0.0:
        return None
    return bbox


def _relative_bbox_to_pascal_voc(
    bbox: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> list[float]:
    x, y, width, height = bbox
    return [
        x * image_width,
        y * image_height,
        (x + width) * image_width,
        (y + height) * image_height,
    ]


def _pascal_voc_to_relative_bbox(
    bbox: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> list[float]:
    x_min, y_min, x_max, y_max = bbox
    return [
        _clamp01(x_min / image_width),
        _clamp01(y_min / image_height),
        _clamp01((x_max - x_min) / image_width),
        _clamp01((y_max - y_min) / image_height),
    ]


def _bbox_pixel_slice(
    bbox: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int] | None:
    x, y, width, height = bbox
    x_min = _bbox_pixel_min(x, limit=image_width)
    y_min = _bbox_pixel_min(y, limit=image_height)
    x_max = _bbox_pixel_max(x + width, limit=image_width)
    y_max = _bbox_pixel_max(y + height, limit=image_height)
    if x_max <= x_min or y_max <= y_min:
        return None
    return x_min, y_min, x_max, y_max


def _bbox_pixel_min(value: float, *, limit: int) -> int:
    return max(0, min(limit, int(np.floor(_clamp01(value) * limit + _PIXEL_COORD_EPSILON))))


def _bbox_pixel_max(value: float, *, limit: int) -> int:
    return max(0, min(limit, int(np.ceil(_clamp01(value) * limit - _PIXEL_COORD_EPSILON))))


def _polyline_points(polyline: fo.Polyline) -> list[list[list[float]]]:
    return [_point_list(shape) for shape in _runtime_sequence(getattr(polyline, "points", None))]


def _polyline_shapes(payload: Mapping[str, object]) -> list[list[list[float]]]:
    return [_point_list(shape) for shape in _payload_sequence(payload, "points")]


def _point_list(value: object) -> list[list[float]]:
    if not isinstance(value, list | tuple):
        return []
    return [point for raw_point in value if len(point := _float_sequence(raw_point)[:2]) >= 2]


def _polyline_min_points(payload: Mapping[str, object]) -> int:
    return (
        3
        if _optional_bool(payload.get("closed"), default=False) or _optional_bool(payload.get("filled"), default=False)
        else 2
    )


def _absolute_point_to_relative(
    point: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> list[float]:
    return [_clamp01(point[0] / image_width), _clamp01(point[1] / image_height)]
