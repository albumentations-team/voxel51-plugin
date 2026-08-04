"""Convert FiftyOne labels to Albumentations targets and back."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import fiftyone as fo
import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.core import JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping, normalize_json_value

ANNOTATION_PAYLOAD_KEY: Final[str] = "annotation_payload"
ANNOTATION_EXCLUDED_FIELDS_KEY: Final[str] = "annotation_excluded_fields"

_TYPE_FIELD: Final[str] = "type"
_CLASSIFICATION_TYPE: Final[str] = "classification"
_DETECTIONS_TYPE: Final[str] = "detections"
_KEYPOINTS_TYPE: Final[str] = "keypoints"
_SEGMENTATION_TYPE: Final[str] = "segmentation"

_SUPPORTED_LABEL_TYPES: Final[tuple[type[fo.Label], ...]] = (
    fo.Classification,
    fo.Detections,
    fo.Keypoints,
    fo.Segmentation,
)

_ImageShape = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class _AnnotationRef:
    field_name: str
    label_index: int
    point_index: int | None = None


@dataclass(frozen=True, slots=True)
class AnnotationTargets:
    """Albumentations target payload plus lookup data for reconstruction."""

    values: Mapping[str, object]
    bbox_refs: tuple[_AnnotationRef, ...] = ()
    keypoint_refs: tuple[_AnnotationRef, ...] = ()
    mask_refs: tuple[_AnnotationRef, ...] = ()


def resolve_annotation_fields(
    dataset: fo.Dataset,
    selected_label_fields: Sequence[str] = (),
) -> tuple[tuple[str, ...], tuple[JSONDict, ...]]:
    """Return supported annotation fields and skipped fields with reasons."""

    schema = dataset.get_field_schema()
    candidates = tuple(str(field_name) for field_name in selected_label_fields) or tuple(schema)
    included: list[str] = []
    excluded: list[JSONDict] = []

    for field_name in candidates:
        field = schema.get(field_name)
        if field is None:
            excluded.append(
                {
                    "field_name": field_name,
                    "reason": "missing_field",
                    "message": "Selected label field does not exist in the dataset schema.",
                }
            )
            continue

        label_type = getattr(field, "document_type", None)
        if not _is_label_type(label_type):
            continue
        if _is_supported_label_type(label_type):
            included.append(field_name)
            continue
        excluded.append(
            {
                "field_name": field_name,
                "label_type": _label_type_name(label_type),
                "reason": "unsupported_label_type",
                "message": "Label field is not supported by annotation-aware augmentation yet.",
            }
        )

    return tuple(included), tuple(excluded)


def annotation_payload_from_sample(sample: fo.Sample, label_fields: Sequence[str]) -> JSONDict:
    """Serialize supported FiftyOne labels from one sample into JSON payload."""

    fields: dict[str, JSONValue] = {}
    for field_name in label_fields:
        label = sample.get_field(field_name)
        if label is None:
            continue
        field_payload = _field_payload(label)
        if field_payload is not None:
            fields[field_name] = field_payload
    return {"fields": fields}


def target_data_from_annotation_payload(payload: Mapping[str, object], image_shape: _ImageShape) -> AnnotationTargets:
    """Build Albumentations targets from a serialized annotation payload."""

    image_height, image_width, _channels = image_shape
    bboxes: list[list[float]] = []
    bbox_indices: list[int] = []
    bbox_refs: list[_AnnotationRef] = []
    keypoints: list[list[float]] = []
    keypoint_indices: list[int] = []
    keypoint_refs: list[_AnnotationRef] = []
    masks: list[npt.NDArray[Any]] = []
    mask_refs: list[_AnnotationRef] = []

    for field_name, field_payload in _payload_fields(payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _DETECTIONS_TYPE:
            for detection_index, detection in enumerate(_payload_sequence(field_payload, "detections")):
                bbox = _relative_bbox(detection)
                if bbox is None:
                    continue
                bboxes.append(_relative_bbox_to_pascal_voc(bbox, image_width=image_width, image_height=image_height))
                bbox_indices.append(len(bbox_refs))
                bbox_refs.append(_AnnotationRef(field_name=field_name, label_index=detection_index))
        elif field_type == _KEYPOINTS_TYPE:
            for keypoint_index, keypoint in enumerate(_payload_sequence(field_payload, "keypoints")):
                for point_index, point in enumerate(_relative_points(keypoint)):
                    keypoints.append([point[0] * image_width, point[1] * image_height])
                    keypoint_indices.append(len(keypoint_refs))
                    keypoint_refs.append(
                        _AnnotationRef(field_name=field_name, label_index=keypoint_index, point_index=point_index)
                    )
        elif field_type == _SEGMENTATION_TYPE:
            mask = _mask_array(field_payload)
            if mask is not None:
                masks.append(mask)
                mask_refs.append(_AnnotationRef(field_name=field_name, label_index=0))

    values: dict[str, object] = {}
    if bboxes:
        values["bboxes"] = bboxes
        values["bbox_indices"] = bbox_indices
    if keypoints:
        values["keypoints"] = keypoints
        values["keypoint_indices"] = keypoint_indices
    if masks:
        values["masks"] = np.stack(masks, axis=0)

    return AnnotationTargets(
        values=values,
        bbox_refs=tuple(bbox_refs),
        keypoint_refs=tuple(keypoint_refs),
        mask_refs=tuple(mask_refs),
    )


def transformed_annotation_payload(
    source_payload: Mapping[str, object],
    target_data: AnnotationTargets,
    output_targets: Mapping[str, object],
    output_shape: _ImageShape,
) -> JSONDict:
    """Build a transformed annotation payload from Albumentations output targets."""

    output_height, output_width, _channels = output_shape
    fields = _copy_static_fields(source_payload)
    dropped = {
        "detections": len(target_data.bbox_refs),
        "keypoints": len(target_data.keypoint_refs),
        "masks": len(target_data.mask_refs),
    }

    for field_name, field_payload in _payload_fields(source_payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _DETECTIONS_TYPE:
            fields[field_name] = {_TYPE_FIELD: _DETECTIONS_TYPE, "detections": []}
        elif field_type == _KEYPOINTS_TYPE:
            fields[field_name] = _empty_keypoints_payload(field_payload)

    for raw_bbox, raw_ref_index in zip(
        _output_sequence(output_targets, "bboxes"),
        _output_sequence(output_targets, "bbox_indices"),
        strict=False,
    ):
        ref = target_data.bbox_refs[_target_index(raw_ref_index)]
        detection = dict(
            _payload_sequence(_payload_fields(source_payload)[ref.field_name], "detections")[ref.label_index]
        )
        detection["bounding_box"] = _pascal_voc_to_relative_bbox(
            _float_sequence(raw_bbox),
            image_width=output_width,
            image_height=output_height,
        )
        field = cast(dict[str, object], fields[ref.field_name])
        detections = cast(list[JSONDict], field["detections"])
        detections.append(normalize_json_mapping(detection))
        dropped["detections"] -= 1

    for raw_point, raw_ref_index in zip(
        _output_sequence(output_targets, "keypoints"),
        _output_sequence(output_targets, "keypoint_indices"),
        strict=False,
    ):
        ref = target_data.keypoint_refs[_target_index(raw_ref_index)]
        field = cast(dict[str, object], fields[ref.field_name])
        keypoints = cast(list[dict[str, object]], field["keypoints"])
        keypoint = keypoints[ref.label_index]
        point = _absolute_point_to_relative(
            _float_sequence(raw_point), image_width=output_width, image_height=output_height
        )
        cast(list[list[float]], keypoint["points"]).append(point)

        source_keypoint = _payload_sequence(_payload_fields(source_payload)[ref.field_name], "keypoints")[
            ref.label_index
        ]
        confidence = _payload_sequence(source_keypoint, "confidence")
        if ref.point_index is not None and ref.point_index < len(confidence):
            cast(list[JSONValue], keypoint["confidence"]).append(normalize_json_value(confidence[ref.point_index]))
        dropped["keypoints"] -= 1

    fields = _drop_empty_keypoints(fields)

    for raw_mask, ref in zip(_output_sequence(output_targets, "masks"), target_data.mask_refs, strict=False):
        fields[ref.field_name] = {
            _TYPE_FIELD: _SEGMENTATION_TYPE,
            "mask": _mask_to_json(raw_mask),
        }
        dropped["masks"] -= 1

    return {
        "fields": normalize_json_mapping(fields),
        "metadata": {
            "dropped_annotations": {name: count for name, count in dropped.items() if count > 0},
        },
    }


def labels_from_annotation_payload(payload: Mapping[str, object]) -> dict[str, fo.Label]:
    """Convert a serialized annotation payload into FiftyOne label objects."""

    labels: dict[str, fo.Label] = {}
    for field_name, field_payload in _payload_fields(payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _CLASSIFICATION_TYPE:
            labels[field_name] = _classification_from_payload(field_payload)
        elif field_type == _DETECTIONS_TYPE:
            labels[field_name] = _detections_from_payload(field_payload)
        elif field_type == _KEYPOINTS_TYPE:
            labels[field_name] = _keypoints_from_payload(field_payload)
        elif field_type == _SEGMENTATION_TYPE:
            labels[field_name] = _segmentation_from_payload(field_payload)
    return labels


def _field_payload(label: object) -> JSONDict | None:
    if isinstance(label, fo.Classification):
        return _classification_payload(label)
    if isinstance(label, fo.Detections):
        return _detections_payload(label)
    if isinstance(label, fo.Keypoints):
        return _keypoints_payload(label)
    if isinstance(label, fo.Segmentation):
        return _segmentation_payload(label)
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
            "attributes": _json_mapping_or_empty(detection.attributes),
        }
    )
    _set_optional(payload, "label", detection.label)
    _set_optional(payload, "confidence", detection.confidence)
    _set_optional(payload, "index", detection.index)
    return payload


def _keypoints_payload(label: fo.Keypoints) -> JSONDict:
    return {
        _TYPE_FIELD: _KEYPOINTS_TYPE,
        "keypoints": [_keypoint_payload(keypoint) for keypoint in _keypoints(label)],
    }


def _keypoint_payload(keypoint: fo.Keypoint) -> JSONDict:
    payload = normalize_json_mapping(
        {
            "points": [_float_sequence(point)[:2] for point in _runtime_sequence(getattr(keypoint, "points", None))],
            "tags": _str_list(getattr(keypoint, "tags", None)),
            "attributes": _json_mapping_or_empty(keypoint.attributes),
        }
    )
    _set_optional(payload, "label", keypoint.label)
    _set_optional(payload, "confidence", _array_or_sequence(keypoint.confidence))
    _set_optional(payload, "index", keypoint.index)
    return payload


def _segmentation_payload(label: fo.Segmentation) -> JSONDict | None:
    if not _has_mask(label):
        return None
    return normalize_json_mapping(
        {
            _TYPE_FIELD: _SEGMENTATION_TYPE,
            "mask": _mask_to_json(label.get_mask()),
            "tags": _str_list(getattr(label, "tags", None)),
        }
    )


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
    detection = fo.Detection(
        label=_optional_str(payload.get("label")),
        bounding_box=_float_sequence(payload.get("bounding_box")),
        confidence=_optional_float(payload.get("confidence")),
        tags=_str_list(payload.get("tags")),
        attributes=_attributes_from_payload(payload.get("attributes")),
    )
    index = payload.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        detection.index = index
    return detection


def _keypoints_from_payload(payload: Mapping[str, object]) -> fo.Keypoints:
    keypoints = [_keypoint_from_payload(item) for item in _payload_sequence(payload, "keypoints")]
    return fo.Keypoints(keypoints=keypoints)


def _keypoint_from_payload(payload: Mapping[str, object]) -> fo.Keypoint:
    keypoint = fo.Keypoint(
        label=_optional_str(payload.get("label")),
        points=[_float_sequence(point) for point in _payload_sequence(payload, "points")],
        confidence=_optional_float_list(payload.get("confidence")),
        tags=_str_list(payload.get("tags")),
        attributes=_attributes_from_payload(payload.get("attributes")),
    )
    index = payload.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        keypoint.index = index
    return keypoint


def _segmentation_from_payload(payload: Mapping[str, object]) -> fo.Segmentation:
    return fo.Segmentation(mask=np.asarray(payload.get("mask"), dtype=np.uint8), tags=_str_list(payload.get("tags")))


def _copy_static_fields(source_payload: Mapping[str, object]) -> dict[str, JSONValue]:
    fields: dict[str, JSONValue] = {}
    for field_name, field_payload in _payload_fields(source_payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _CLASSIFICATION_TYPE:
            fields[field_name] = normalize_json_mapping(field_payload)
    return fields


def _empty_keypoints_payload(field_payload: Mapping[str, object]) -> JSONDict:
    keypoints = []
    for source_keypoint in _payload_sequence(field_payload, "keypoints"):
        keypoint = dict(source_keypoint)
        keypoint["points"] = []
        if "confidence" in keypoint:
            keypoint["confidence"] = []
        keypoints.append(normalize_json_mapping(keypoint))
    return normalize_json_mapping({_TYPE_FIELD: _KEYPOINTS_TYPE, "keypoints": keypoints})


def _drop_empty_keypoints(fields: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    updated = dict(fields)
    for field_name, field_payload in tuple(updated.items()):
        if not isinstance(field_payload, Mapping) or _payload_type(field_payload) != _KEYPOINTS_TYPE:
            continue
        keypoints = [
            keypoint
            for keypoint in _payload_sequence(field_payload, "keypoints")
            if _payload_sequence(keypoint, "points")
        ]
        updated[field_name] = {_TYPE_FIELD: _KEYPOINTS_TYPE, "keypoints": keypoints}
    return updated


def _payload_fields(payload: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        return {}
    return {
        str(field_name): field_payload
        for field_name, field_payload in fields.items()
        if isinstance(field_payload, Mapping)
    }


def _payload_type(payload: Mapping[str, object]) -> str:
    value = payload.get(_TYPE_FIELD)
    return value if isinstance(value, str) else ""


def _payload_sequence(payload: Mapping[str, object], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list | tuple) else []


def _runtime_sequence(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return list(value)
    return list(cast(Sequence[Any], value))


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


def _output_sequence(payload: Mapping[str, object], key: str) -> list[Any]:
    value = payload.get(key)
    if isinstance(value, np.ndarray):
        return list(value)
    return list(value) if isinstance(value, list | tuple) else []


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


def _relative_points(payload: Mapping[str, object]) -> list[list[float]]:
    return [
        _float_sequence(point)[:2] for point in _payload_sequence(payload, "points") if len(_float_sequence(point)) >= 2
    ]


def _absolute_point_to_relative(
    point: Sequence[float],
    *,
    image_width: int,
    image_height: int,
) -> list[float]:
    return [_clamp01(point[0] / image_width), _clamp01(point[1] / image_height)]


def _float_sequence(value: object) -> list[float]:
    if not isinstance(value, list | tuple | np.ndarray):
        return []
    result: list[float] = []
    for item in value:
        if isinstance(item, int | float | np.integer | np.floating) and not isinstance(item, bool):
            result.append(float(item))
    return result


def _target_index(value: object) -> int:
    if isinstance(value, int | float | np.integer | np.floating) and not isinstance(value, bool):
        return int(round(float(value)))
    raise TypeError(f"Unsupported annotation target index: {value!r}")


def _mask_array(payload: Mapping[str, object]) -> npt.NDArray[Any] | None:
    value = payload.get("mask")
    if value is None:
        return None
    return np.asarray(value)


def _has_mask(label: fo.Segmentation) -> bool:
    value = label.has_mask
    return bool(value() if callable(value) else value)


def _mask_to_json(mask: object) -> list[JSONValue]:
    return cast(list[JSONValue], np.asarray(mask).tolist())


def _array_or_sequence(value: object) -> JSONValue:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return normalize_json_value(value.tolist())
    return normalize_json_value(value)


def _optional_array(value: object) -> npt.NDArray[np.float32] | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32)


def _optional_float_list(value: object) -> list[float] | None:
    if value is None:
        return None
    return _float_sequence(value)


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


def _mapping(value: object) -> Mapping[str, JSONValue]:
    return value if isinstance(value, Mapping) else {}


def _json_mapping_or_empty(value: object) -> JSONDict:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, JSONValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        raw_value = getattr(item, "value", item)
        try:
            normalized[key] = normalize_json_value(raw_value)
        except TypeError:
            normalized[key] = str(raw_value)
    return normalized


def _attributes_from_payload(value: object) -> dict[str, fo.Attribute]:
    attributes: dict[str, fo.Attribute] = {}
    if not isinstance(value, Mapping):
        return attributes
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, bool):
            attributes[key] = fo.BooleanAttribute(value=item)
        elif isinstance(item, int | float) and not isinstance(item, bool):
            attributes[key] = fo.NumericAttribute(value=float(item))
        elif isinstance(item, str):
            attributes[key] = fo.CategoricalAttribute(value=item)
        else:
            attributes[key] = fo.CategoricalAttribute(value=str(item))
    return attributes


def _set_optional(payload: dict[str, JSONValue], key: str, value: object) -> None:
    if value is not None:
        payload[key] = normalize_json_value(value)


def _is_label_type(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, fo.Label)


def _is_supported_label_type(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, _SUPPORTED_LABEL_TYPES)


def _label_type_name(value: object) -> str:
    return value.__name__ if isinstance(value, type) else type(value).__name__


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
