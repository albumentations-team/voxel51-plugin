"""Target references and shared annotation payload keys."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    FIELD_TYPE_CLASSIFICATION,
    FIELD_TYPE_DETECTIONS,
    FIELD_TYPE_HEATMAP,
    FIELD_TYPE_KEYPOINTS,
    FIELD_TYPE_POLYLINES,
    FIELD_TYPE_SEGMENTATION,
)

_TYPE_FIELD: Final[str] = "type"
_CLASSIFICATION_TYPE: Final[str] = FIELD_TYPE_CLASSIFICATION
_DETECTIONS_TYPE: Final[str] = FIELD_TYPE_DETECTIONS
_HEATMAP_TYPE: Final[str] = FIELD_TYPE_HEATMAP
_KEYPOINTS_TYPE: Final[str] = FIELD_TYPE_KEYPOINTS
_POLYLINES_TYPE: Final[str] = FIELD_TYPE_POLYLINES
_SEGMENTATION_TYPE: Final[str] = FIELD_TYPE_SEGMENTATION
_HEATMAPS_TARGET_FIELD: Final[str] = "heatmaps"
_HEATMAP_MAP_FIELD: Final[str] = "map"
_HEATMAP_MAP_PATH_FIELD: Final[str] = "map_path"
_HEATMAP_SOURCE_MAP_PATH_FIELD: Final[str] = "source_map_path"
_MASK_FIELD: Final[str] = "mask"
_SEGMENTATION_MASK_PATH_FIELD: Final[str] = "mask_path"
_SEGMENTATION_SOURCE_MASK_PATH_FIELD: Final[str] = "source_mask_path"
_PIXEL_COORD_EPSILON: Final[float] = 1e-6
_ImageShape = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class _AnnotationRef:
    field_name: str
    label_index: int
    shape_index: int | None = None
    point_index: int | None = None


@dataclass(frozen=True, slots=True)
class AnnotationTargets:
    """Albumentations target payload plus lookup data for reconstruction."""

    values: Mapping[str, object]
    bbox_refs: tuple[_AnnotationRef, ...] = ()
    heatmap_refs: tuple[_AnnotationRef, ...] = ()
    keypoint_refs: tuple[_AnnotationRef, ...] = ()
    mask_refs: tuple[_AnnotationRef, ...] = ()
