"""Serialize and reconstruct FiftyOne label objects."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import fiftyone as fo
import numpy as np

from albumentationsx_plugin.core import HostAdapterError, JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping, normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations.arrays import (
    _detection_mask,
    _has_heatmap,
    _has_mask,
    _heatmap_map,
    _heatmap_map_path,
    _heatmap_payload_array,
    _heatmap_to_json,
    _instance_mask_array,
    _mask_array,
    _mask_to_json,
    _segmentation_mask,
    _segmentation_mask_path,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.geometry import _polyline_points, _polyline_shapes
from albumentationsx_plugin.hosts.fiftyone.annotations.metadata import (
    capture_label_metadata,
    restore_label_metadata,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.payload_values import (
    _array_or_sequence,
    _float_sequence,
    _optional_array,
    _optional_bool,
    _optional_float,
    _optional_heatmap_range,
    _optional_str,
    _payload_fields,
    _payload_sequence,
    _payload_type,
    _runtime_sequence,
    _set_optional,
    _str_list,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.target_types import (
    _CLASSIFICATION_TYPE,
    _DETECTIONS_TYPE,
    _HEATMAP_MAP_FIELD,
    _HEATMAP_MAP_PATH_FIELD,
    _HEATMAP_TYPE,
    _KEYPOINTS_TYPE,
    _MASK_FIELD,
    _POLYLINES_TYPE,
    _SEGMENTATION_MASK_PATH_FIELD,
    _SEGMENTATION_TYPE,
    _TYPE_FIELD,
)


def annotation_payload_from_sample(sample: fo.Sample, label_fields: Sequence[str]) -> JSONDict:
    """Serialize supported FiftyOne labels from one sample into JSON payload."""

    fields: dict[str, JSONValue] = {}
    for field_name in label_fields:
        label = sample.get_field(field_name)
        if label is None:
            continue
        try:
            field_payload = _field_payload(label)
        except (TypeError, ValueError) as error:
            raise HostAdapterError(
                host="fiftyone",
                message=(
                    f"Cannot read annotation field '{field_name}' on sample {sample.id}: {error}. "
                    "Correct the annotation or deselect this field and retry."
                ),
                context={
                    "reason": "invalid_annotation_data",
                    "sample_id": str(sample.id),
                    "field_name": field_name,
                },
            ) from error
        if field_payload is not None:
            fields[field_name] = field_payload
    return {"fields": fields}


def labels_from_annotation_payload(payload: Mapping[str, object]) -> dict[str, fo.Label]:
    """Convert a serialized annotation payload into FiftyOne label objects."""

    labels: dict[str, fo.Label] = {}
    for field_name, field_payload in _payload_fields(payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _CLASSIFICATION_TYPE:
            labels[field_name] = _classification_from_payload(field_payload)
        elif field_type == _DETECTIONS_TYPE:
            labels[field_name] = _detections_from_payload(field_payload)
        elif field_type == _HEATMAP_TYPE:
            labels[field_name] = _heatmap_from_payload(field_payload)
        elif field_type == _KEYPOINTS_TYPE:
            labels[field_name] = _keypoints_from_payload(field_payload)
        elif field_type == _POLYLINES_TYPE:
            labels[field_name] = _polylines_from_payload(field_payload)
        elif field_type == _SEGMENTATION_TYPE:
            labels[field_name] = _segmentation_from_payload(field_payload)
    return {name: restore_label_metadata(label, _payload_fields(payload)[name]) for name, label in labels.items()}


def _field_payload(label: object) -> JSONDict | None:
    if isinstance(label, fo.Classification):
        return capture_label_metadata(label, _classification_payload(label))
    if isinstance(label, fo.Detections):
        return capture_label_metadata(label, _detections_payload(label))
    if isinstance(label, fo.Heatmap):
        payload = _heatmap_payload(label)
        return capture_label_metadata(label, payload) if payload is not None else None
    if isinstance(label, fo.Keypoints):
        return capture_label_metadata(label, _keypoints_payload(label))
    if isinstance(label, fo.Polylines):
        return capture_label_metadata(label, _polylines_payload(label))
    if isinstance(label, fo.Segmentation):
        payload = _segmentation_payload(label)
        return capture_label_metadata(label, payload) if payload is not None else None
    return None


def _classification_payload(label: fo.Classification) -> JSONDict:
    payload = normalize_json_mapping(
        {_TYPE_FIELD: _CLASSIFICATION_TYPE, "tags": _str_list(getattr(label, "tags", None))}
    )
    _set_optional(payload, "label", label.label)
    _set_optional(payload, "confidence", label.confidence)
    _set_optional(payload, "logits", _array_or_sequence(label.logits))
    return payload


def _detections_payload(label: fo.Detections) -> JSONDict:
    return {
        _TYPE_FIELD: _DETECTIONS_TYPE,
        "detections": [_detection_payload(detection) for detection in _detections(label)],
    }


def _detection_payload(detection: fo.Detection) -> JSONDict:
    payload = normalize_json_mapping(
        {
            "bounding_box": _float_sequence(getattr(detection, "bounding_box", None)),
            "tags": _str_list(getattr(detection, "tags", None)),
        }
    )
    _set_optional(payload, "label", detection.label)
    _set_optional(payload, "confidence", detection.confidence)
    _set_optional(payload, "index", detection.index)
    mask = _detection_mask(detection)
    if mask is not None:
        payload[_MASK_FIELD] = _mask_to_json(_instance_mask_array(mask))
    return capture_label_metadata(detection, payload)


def _heatmap_payload(label: fo.Heatmap) -> JSONDict | None:
    if not _has_heatmap(label):
        return None
    payload: dict[str, object] = {
        _TYPE_FIELD: _HEATMAP_TYPE,
        _HEATMAP_MAP_FIELD: _heatmap_to_json(_heatmap_map(label)),
        "tags": _str_list(getattr(label, "tags", None)),
    }
    _set_optional(payload, _HEATMAP_MAP_PATH_FIELD, _heatmap_map_path(label))
    _set_optional(payload, "range", _optional_heatmap_range(getattr(label, "range", None)))
    return normalize_json_mapping(payload)


def _keypoints_payload(label: fo.Keypoints) -> JSONDict:
    keypoints: list[JSONValue] = []
    for index, keypoint in enumerate(_keypoints(label)):
        try:
            keypoints.append(_keypoint_payload(keypoint))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Keypoint {index}: {error}") from error
    return {_TYPE_FIELD: _KEYPOINTS_TYPE, "keypoints": keypoints}


def _keypoint_payload(keypoint: fo.Keypoint) -> JSONDict:
    points = [
        _keypoint_point(point, index)
        for index, point in enumerate(_runtime_sequence(getattr(keypoint, "points", None)))
    ]
    payload = normalize_json_mapping(
        {
            "points": points,
            "tags": _str_list(getattr(keypoint, "tags", None)),
        }
    )
    _set_optional(payload, "label", keypoint.label)
    for name in ("confidence", "visible"):
        values = _keypoint_values(getattr(keypoint, name, None), name=name, point_count=len(points))
        _set_optional(payload, name, values)
    _set_optional(payload, "index", keypoint.index)
    return capture_label_metadata(keypoint, payload)


def _keypoint_point(value: object, index: int) -> list[float] | None:
    """Encode a missing point as JSON null, keeping its anatomical slot."""

    if value is None:
        return None
    if not isinstance(value, list | tuple | np.ndarray) or len(value) != 2:
        raise ValueError(f"Point {index} must contain exactly two coordinates")
    point = _float_sequence(value)
    if len(point) != 2:
        raise ValueError(f"Point {index} must contain numeric coordinates")
    if all(math.isnan(coordinate) for coordinate in point):
        return None
    if not all(math.isfinite(coordinate) and 0 <= coordinate <= 1 for coordinate in point):
        raise ValueError(f"Point {index} requires finite coordinates in [0, 1] or a missing (NaN, NaN) pair")
    return point


def _keypoint_values(value: object, *, name: str, point_count: int) -> JSONValue:
    if value is None:
        return None
    values = value.tolist() if isinstance(value, np.ndarray) else value
    if not isinstance(values, list | tuple) or len(values) != point_count:
        raise ValueError(f"{name} must contain one value per point ({point_count} values)")
    try:
        return normalize_json_value(values)
    except TypeError as error:
        raise ValueError(f"Invalid {name}: {error}") from error


def _polylines_payload(label: fo.Polylines) -> JSONDict:
    return {
        _TYPE_FIELD: _POLYLINES_TYPE,
        "polylines": [_polyline_payload(polyline) for polyline in _polylines(label)],
    }


def _polyline_payload(polyline: fo.Polyline) -> JSONDict:
    payload = normalize_json_mapping(
        {
            "points": _polyline_points(polyline),
            "tags": _str_list(getattr(polyline, "tags", None)),
            "closed": bool(getattr(polyline, "closed", False)),
            "filled": bool(getattr(polyline, "filled", False)),
        }
    )
    _set_optional(payload, "label", polyline.label)
    _set_optional(payload, "confidence", polyline.confidence)
    _set_optional(payload, "index", polyline.index)
    return capture_label_metadata(polyline, payload)


def _segmentation_payload(label: fo.Segmentation) -> JSONDict | None:
    if not _has_mask(label):
        return None
    payload: dict[str, object] = {
        _TYPE_FIELD: _SEGMENTATION_TYPE,
        _MASK_FIELD: _mask_to_json(_segmentation_mask(label)),
        "tags": _str_list(getattr(label, "tags", None)),
    }
    _set_optional(payload, _SEGMENTATION_MASK_PATH_FIELD, _segmentation_mask_path(label))
    return normalize_json_mapping(payload)


def _classification_from_payload(payload: Mapping[str, object]) -> fo.Classification:
    return fo.Classification(
        label=_optional_str(payload.get("label")),
        confidence=_optional_float(payload.get("confidence")),
        logits=_optional_array(payload.get("logits")),
        tags=_str_list(payload.get("tags")),
    )


def _detections_from_payload(payload: Mapping[str, object]) -> fo.Detections:
    detections = [_detection_from_payload(item) for item in _payload_sequence(payload, "detections")]
    return fo.Detections(detections=detections)


def _detection_from_payload(payload: Mapping[str, object]) -> fo.Detection:
    mask = _mask_array(payload)
    detection = fo.Detection(
        label=_optional_str(payload.get("label")),
        bounding_box=_float_sequence(payload.get("bounding_box")),
        mask=None if mask is None else np.asarray(mask),
        confidence=_optional_float(payload.get("confidence")),
        tags=_str_list(payload.get("tags")),
    )
    index = payload.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        detection.index = index
    return restore_label_metadata(detection, payload)


def _heatmap_from_payload(payload: Mapping[str, object]) -> fo.Heatmap:
    tags = _str_list(payload.get("tags"))
    heatmap_range = _optional_heatmap_range(payload.get("range"))
    map_path = _optional_str(payload.get(_HEATMAP_MAP_PATH_FIELD))
    if map_path:
        return fo.Heatmap(map_path=map_path, range=heatmap_range, tags=tags)

    heatmap = _heatmap_payload_array(payload)
    if heatmap is None:
        return fo.Heatmap(tags=tags)
    return fo.Heatmap(map=heatmap, range=heatmap_range, tags=tags)


def _keypoints_from_payload(payload: Mapping[str, object]) -> fo.Keypoints:
    keypoints = [_keypoint_from_payload(item) for item in _payload_sequence(payload, "keypoints")]
    return fo.Keypoints(keypoints=keypoints)


def _keypoint_from_payload(payload: Mapping[str, object]) -> fo.Keypoint:
    keypoint = fo.Keypoint(
        label=_optional_str(payload.get("label")),
        points=[
            [float("nan"), float("nan")] if point is None else _float_sequence(point)
            for point in _payload_sequence(payload, "points")
        ],
        confidence=None if payload.get("confidence") is None else _payload_sequence(payload, "confidence"),
        tags=_str_list(payload.get("tags")),
    )
    index = payload.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        keypoint.index = index
    if "visible" in payload:
        keypoint["visible"] = _payload_sequence(payload, "visible")
    return restore_label_metadata(keypoint, payload)


def _polylines_from_payload(payload: Mapping[str, object]) -> fo.Polylines:
    polylines = [_polyline_from_payload(item) for item in _payload_sequence(payload, "polylines")]
    return fo.Polylines(polylines=polylines)


def _polyline_from_payload(payload: Mapping[str, object]) -> fo.Polyline:
    polyline = fo.Polyline(
        label=_optional_str(payload.get("label")),
        points=_polyline_shapes(payload),
        confidence=_optional_float(payload.get("confidence")),
        tags=_str_list(payload.get("tags")),
        closed=_optional_bool(payload.get("closed"), default=False),
        filled=_optional_bool(payload.get("filled"), default=False),
    )
    index = payload.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        polyline.index = index
    return restore_label_metadata(polyline, payload)


def _segmentation_from_payload(payload: Mapping[str, object]) -> fo.Segmentation:
    tags = _str_list(payload.get("tags"))
    mask_path = _optional_str(payload.get(_SEGMENTATION_MASK_PATH_FIELD))
    if mask_path:
        return fo.Segmentation(mask_path=mask_path, tags=tags)

    mask = _mask_array(payload)
    if mask is None:
        return fo.Segmentation(tags=tags)
    return fo.Segmentation(mask=np.asarray(mask), tags=tags)


def _detections(label: fo.Detections) -> list[fo.Detection]:
    return [
        detection
        for detection in _runtime_sequence(getattr(label, "detections", None))
        if isinstance(detection, fo.Detection)
    ]


def _keypoints(label: fo.Keypoints) -> list[fo.Keypoint]:
    return [
        keypoint
        for keypoint in _runtime_sequence(getattr(label, "keypoints", None))
        if isinstance(keypoint, fo.Keypoint)
    ]


def _polylines(label: fo.Polylines) -> list[fo.Polyline]:
    return [
        polyline
        for polyline in _runtime_sequence(getattr(label, "polylines", None))
        if isinstance(polyline, fo.Polyline)
    ]
