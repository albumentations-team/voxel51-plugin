"""Build field-level annotation comparison summaries for preview outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    FIELD_TYPE_CLASSIFICATION,
    FIELD_TYPE_DETECTIONS,
    FIELD_TYPE_HEATMAP,
    FIELD_TYPE_KEYPOINTS,
    FIELD_TYPE_POLYLINES,
    FIELD_TYPE_SEGMENTATION,
)

_TYPE_FIELD: Final[str] = "type"
_FIELDS_FIELD: Final[str] = "fields"
_METADATA_FIELD: Final[str] = "metadata"
_DROPPED_ANNOTATIONS_FIELD: Final[str] = "dropped_annotations"


@dataclass(frozen=True, slots=True)
class AnnotationFieldCount:
    """Count labels and spatial primitives in one serialized annotation field."""

    label_type: str
    annotation_count: int
    geometry_count: int


def build_preview_annotation_comparison(
    source_payload: Mapping[str, object],
    output_payload: Mapping[str, object],
) -> JSONDict:
    """Return field-level before/after annotation diagnostics for preview."""

    source_fields = payload_fields(source_payload)
    output_fields = payload_fields(output_payload)
    rows: list[JSONDict] = []
    source_annotation_total = 0
    output_annotation_total = 0
    source_geometry_total = 0
    output_geometry_total = 0
    for field_name in sorted(set(source_fields) | set(output_fields)):
        source_field = source_fields.get(field_name, {})
        output_field = output_fields.get(field_name, {})
        source_count = field_count(source_field)
        output_count = field_count(output_field)
        source_annotation_total += source_count.annotation_count
        output_annotation_total += output_count.annotation_count
        source_geometry_total += source_count.geometry_count
        output_geometry_total += output_count.geometry_count
        rows.append(
            {
                "field_name": field_name,
                "label_type": source_count.label_type or output_count.label_type,
                "status": field_status(source_field, output_field, source_count, output_count),
                "source_annotation_count": source_count.annotation_count,
                "output_annotation_count": output_count.annotation_count,
                "source_geometry_count": source_count.geometry_count,
                "output_geometry_count": output_count.geometry_count,
                "rendered_overlay": is_spatial_type(source_count.label_type or output_count.label_type),
            }
        )

    return normalize_json_mapping(
        {
            "fields": rows,
            "totals": {
                "source_annotations": source_annotation_total,
                "output_annotations": output_annotation_total,
                "source_geometry": source_geometry_total,
                "output_geometry": output_geometry_total,
            },
            "dropped_annotations": dropped_annotations(output_payload),
        }
    )


def field_status(
    source_field: Mapping[str, object],
    output_field: Mapping[str, object],
    source_count: AnnotationFieldCount,
    output_count: AnnotationFieldCount,
) -> str:
    """Return a compact preview status for one annotation field."""

    if source_count.annotation_count == 0 and output_count.annotation_count == 0:
        return "empty"
    if source_count.annotation_count > 0 and output_count.annotation_count == 0:
        return "dropped"
    if source_count.annotation_count == 0 and output_count.annotation_count > 0:
        return "created"
    if normalize_json_mapping(source_field) == normalize_json_mapping(output_field):
        return "copied"
    return "transformed"


def field_count(field_payload: Mapping[str, object]) -> AnnotationFieldCount:
    """Count labels and geometry primitives for a serialized annotation field."""

    label_type = payload_type(field_payload)
    if label_type == FIELD_TYPE_CLASSIFICATION:
        return AnnotationFieldCount(label_type=label_type, annotation_count=1, geometry_count=0)
    if label_type == FIELD_TYPE_DETECTIONS:
        detections = payload_sequence(field_payload, "detections")
        return AnnotationFieldCount(
            label_type=label_type,
            annotation_count=len(detections),
            geometry_count=len([detection for detection in detections if relative_bbox(detection) is not None]),
        )
    if label_type == FIELD_TYPE_HEATMAP:
        return AnnotationFieldCount(label_type=label_type, annotation_count=1, geometry_count=1)
    if label_type == FIELD_TYPE_KEYPOINTS:
        keypoints = payload_sequence(field_payload, "keypoints")
        return AnnotationFieldCount(
            label_type=label_type,
            annotation_count=len(keypoints),
            geometry_count=sum(len(relative_points(keypoint)) for keypoint in keypoints),
        )
    if label_type == FIELD_TYPE_POLYLINES:
        polylines = payload_sequence(field_payload, "polylines")
        return AnnotationFieldCount(
            label_type=label_type,
            annotation_count=len(polylines),
            geometry_count=sum(len(shape) for polyline in polylines for shape in polyline_shapes(polyline)),
        )
    if label_type == FIELD_TYPE_SEGMENTATION:
        return AnnotationFieldCount(label_type=label_type, annotation_count=1, geometry_count=1)
    return AnnotationFieldCount(label_type=label_type, annotation_count=0, geometry_count=0)


def payload_fields(payload: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    """Return serialized label fields from a payload."""

    fields = payload.get(_FIELDS_FIELD)
    if not isinstance(fields, Mapping):
        return {}
    return {
        str(field_name): field_payload
        for field_name, field_payload in fields.items()
        if isinstance(field_payload, Mapping)
    }


def payload_type(payload: Mapping[str, object]) -> str:
    """Return the serialized FiftyOne label type."""

    value = payload.get(_TYPE_FIELD)
    return value if isinstance(value, str) else ""


def payload_sequence(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    """Return a list of mapping items from one serialized field sequence."""

    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def relative_bbox(payload: Mapping[str, object]) -> tuple[float, float, float, float] | None:
    """Return a valid relative bbox as ``x, y, width, height``."""

    values = float_sequence(payload.get("bounding_box"))
    if len(values) != 4:
        return None
    x, y, width, height = values
    if width <= 0.0 or height <= 0.0:
        return None
    return x, y, width, height


def relative_points(payload: Mapping[str, object]) -> list[tuple[float, float]]:
    """Return valid relative points from a serialized keypoint label."""

    points = []
    for raw_point in object_sequence(payload.get("points")):
        values = float_sequence(raw_point)
        if len(values) >= 2:
            points.append((values[0], values[1]))
    return points


def polyline_shapes(payload: Mapping[str, object]) -> list[list[tuple[float, float]]]:
    """Return valid relative polyline shapes from a serialized polyline label."""

    shapes = []
    for raw_shape in object_sequence(payload.get("points")):
        if not isinstance(raw_shape, list | tuple):
            continue
        shape = []
        for raw_point in raw_shape:
            values = float_sequence(raw_point)
            if len(values) >= 2:
                shape.append((values[0], values[1]))
        if shape:
            shapes.append(shape)
    return shapes


def object_sequence(value: object) -> list[object]:
    """Return a list from a JSON-like sequence value."""

    return list(value) if isinstance(value, list | tuple) else []


def float_sequence(value: object) -> list[float]:
    """Return numeric items from a JSON-like sequence."""

    if not isinstance(value, list | tuple | np.ndarray):
        return []
    result = []
    for item in value:
        if isinstance(item, int | float | np.integer | np.floating) and not isinstance(item, bool):
            result.append(float(item))
    return result


def mask_array(value: object) -> npt.NDArray[np.bool_] | None:
    """Return a boolean mask array from serialized mask data."""

    if value is None:
        return None
    array = np.asarray(value)
    if array.ndim == 3:
        array = array[:, :, 0]
    if array.ndim != 2 or array.size == 0:
        return None
    return np.asarray(array != 0, dtype=np.bool_)


def heatmap_array(value: object) -> npt.NDArray[np.float32] | None:
    """Return a finite 2D heatmap array from serialized heatmap data."""

    if value is None:
        return None
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]
    if array.ndim != 2 or array.size == 0:
        return None
    finite = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    return np.asarray(finite, dtype=np.float32)


def dropped_annotations(payload: Mapping[str, object]) -> JSONDict:
    """Return dropped annotation metadata from a transformed payload."""

    metadata = payload.get(_METADATA_FIELD)
    if not isinstance(metadata, Mapping):
        return {}
    dropped = metadata.get(_DROPPED_ANNOTATIONS_FIELD)
    return normalize_json_mapping(dropped) if isinstance(dropped, Mapping) else {}


def is_spatial_type(label_type: str) -> bool:
    """Return whether this label type can be represented in image overlays."""

    return label_type in {
        FIELD_TYPE_DETECTIONS,
        FIELD_TYPE_HEATMAP,
        FIELD_TYPE_KEYPOINTS,
        FIELD_TYPE_POLYLINES,
        FIELD_TYPE_SEGMENTATION,
    }


def optional_bool(value: object, *, default: bool) -> bool:
    """Return a bool payload value or fallback."""

    return value if isinstance(value, bool) else default


def optional_text(value: object) -> str:
    """Return a string payload value or empty text."""

    return value if isinstance(value, str) else ""
