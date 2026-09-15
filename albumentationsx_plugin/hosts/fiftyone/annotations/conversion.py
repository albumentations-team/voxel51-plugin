"""Convert neutral label payloads into aligned Albumentations targets and back."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.core import JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping, normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations.arrays import (
    _full_image_detection_mask,
    _heatmap_output_array,
    _heatmap_target_array,
    _heatmap_to_json,
    _mask_array,
    _mask_to_json,
    _output_detection_mask,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.geometry import (
    _absolute_point_to_relative,
    _pascal_voc_to_relative_bbox,
    _point_list,
    _polyline_min_points,
    _polyline_shapes,
    _relative_bbox,
    _relative_bbox_to_pascal_voc,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.label_codec import _keypoint_point
from albumentationsx_plugin.hosts.fiftyone.annotations.label_codec import (
    annotation_payload_from_sample as annotation_payload_from_sample,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.label_codec import (
    labels_from_annotation_payload as labels_from_annotation_payload,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.metadata import (
    excluded_label_metadata,
    metadata_fields,
    remove_geometry_metadata,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.payload_values import (
    _float_sequence,
    _optional_heatmap_range,
    _optional_str,
    _output_sequence,
    _payload_fields,
    _payload_sequence,
    _payload_type,
    _set_optional,
    _str_list,
    _target_index,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.target_types import (
    _CLASSIFICATION_TYPE,
    _DETECTIONS_TYPE,
    _HEATMAP_MAP_FIELD,
    _HEATMAP_MAP_PATH_FIELD,
    _HEATMAP_SOURCE_MAP_PATH_FIELD,
    _HEATMAP_TYPE,
    _HEATMAPS_TARGET_FIELD,
    _KEYPOINTS_TYPE,
    _MASK_FIELD,
    _POLYLINES_TYPE,
    _SEGMENTATION_MASK_PATH_FIELD,
    _SEGMENTATION_SOURCE_MASK_PATH_FIELD,
    _SEGMENTATION_TYPE,
    _TYPE_FIELD,
    AnnotationTargets,
    _AnnotationRef,
    _ImageShape,
)


def target_data_from_annotation_payload(
    payload: Mapping[str, object],
    image_shape: _ImageShape,
    label_fields: Sequence[str] | None = None,
) -> AnnotationTargets:
    """Build Albumentations targets from a serialized annotation payload."""

    image_height, image_width, _channels = image_shape
    selected_fields = None if label_fields is None else set(str(field_name) for field_name in label_fields)
    bboxes: list[list[float]] = []
    bbox_indices: list[int] = []
    bbox_refs: list[_AnnotationRef] = []
    heatmaps: list[npt.NDArray[np.float32]] = []
    heatmap_refs: list[_AnnotationRef] = []
    keypoints: list[list[float]] = []
    keypoint_indices: list[int] = []
    keypoint_refs: list[_AnnotationRef] = []
    masks: list[npt.NDArray[Any]] = []
    mask_refs: list[_AnnotationRef] = []

    for field_name, field_payload in _payload_fields(payload).items():
        if selected_fields is not None and field_name not in selected_fields:
            continue
        field_type = _payload_type(field_payload)
        if field_type == _DETECTIONS_TYPE:
            for detection_index, detection in enumerate(_payload_sequence(field_payload, "detections")):
                bbox = _relative_bbox(detection)
                if bbox is None:
                    continue
                bboxes.append(_relative_bbox_to_pascal_voc(bbox, image_width=image_width, image_height=image_height))
                bbox_indices.append(len(bbox_refs))
                detection_ref = _AnnotationRef(field_name=field_name, label_index=detection_index)
                bbox_refs.append(detection_ref)
                instance_mask = _full_image_detection_mask(
                    detection,
                    bbox,
                    image_width=image_width,
                    image_height=image_height,
                )
                if instance_mask is not None:
                    masks.append(instance_mask)
                    mask_refs.append(detection_ref)
        elif field_type == _HEATMAP_TYPE:
            heatmap = _heatmap_target_array(field_payload)
            if heatmap is not None:
                heatmaps.append(heatmap)
                heatmap_refs.append(_AnnotationRef(field_name=field_name, label_index=0))
        elif field_type == _KEYPOINTS_TYPE:
            for keypoint_index, keypoint in enumerate(_payload_sequence(field_payload, "keypoints")):
                for point_index, raw_point in enumerate(_payload_sequence(keypoint, "points")):
                    point = _keypoint_point(raw_point, point_index)
                    if point is None:
                        continue
                    # FiftyOne accepts the normalized endpoints; Albumentations
                    # requires pixel coordinates inside [0, width/height).
                    keypoints.append(
                        [min(point[0] * image_width, image_width - 1), min(point[1] * image_height, image_height - 1)]
                    )
                    keypoint_indices.append(len(keypoint_refs))
                    keypoint_refs.append(
                        _AnnotationRef(field_name=field_name, label_index=keypoint_index, point_index=point_index)
                    )
        elif field_type == _POLYLINES_TYPE:
            for polyline_index, polyline in enumerate(_payload_sequence(field_payload, "polylines")):
                for shape_index, shape in enumerate(_polyline_shapes(polyline)):
                    for point_index, point in enumerate(shape):
                        keypoints.append([point[0] * image_width, point[1] * image_height])
                        keypoint_indices.append(len(keypoint_refs))
                        keypoint_refs.append(
                            _AnnotationRef(
                                field_name=field_name,
                                label_index=polyline_index,
                                shape_index=shape_index,
                                point_index=point_index,
                            )
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
    if heatmaps:
        values[_HEATMAPS_TARGET_FIELD] = np.stack(heatmaps, axis=0)
    if keypoints:
        values["keypoints"] = keypoints
        values["keypoint_indices"] = keypoint_indices
    if masks:
        values["masks"] = np.stack(masks, axis=0)

    return AnnotationTargets(
        values=values,
        bbox_refs=tuple(bbox_refs),
        heatmap_refs=tuple(heatmap_refs),
        keypoint_refs=tuple(keypoint_refs),
        mask_refs=tuple(mask_refs),
    )


def transformed_annotation_payload(
    source_payload: Mapping[str, object],
    target_data: AnnotationTargets,
    output_targets: Mapping[str, object],
    output_shape: _ImageShape,
    copy_label_fields: Sequence[str] = (),
) -> JSONDict:
    """Build a transformed annotation payload from Albumentations output targets."""

    output_height, output_width, _channels = output_shape
    copied_field_names = set(str(field_name) for field_name in copy_label_fields)
    transformed_fields = tuple(
        name
        for name, field in _payload_fields(source_payload).items()
        if name not in copied_field_names and _payload_type(field) != _CLASSIFICATION_TYPE
    )
    excluded_metadata = excluded_label_metadata(_payload_fields(source_payload), transformed_fields=transformed_fields)
    fields: dict[str, object] = {**_copy_static_fields(source_payload, copy_label_fields=copy_label_fields)}
    dropped = {
        "detections": len(target_data.bbox_refs),
        "heatmaps": len(target_data.heatmap_refs),
        "keypoints": _target_ref_count_by_field_type(target_data.keypoint_refs, source_payload, _KEYPOINTS_TYPE),
        "polyline_points": _target_ref_count_by_field_type(
            target_data.keypoint_refs,
            source_payload,
            _POLYLINES_TYPE,
        ),
        "masks": len(target_data.mask_refs),
    }
    output_masks_by_ref = _output_masks_by_ref(target_data, output_targets)

    for field_name, field_payload in _payload_fields(source_payload).items():
        if field_name in copied_field_names:
            continue
        field_type = _payload_type(field_payload)
        if field_type == _DETECTIONS_TYPE:
            fields[field_name] = {**metadata_fields(field_payload), _TYPE_FIELD: _DETECTIONS_TYPE, "detections": []}
        elif field_type == _HEATMAP_TYPE:
            fields[field_name] = _empty_heatmap_payload(field_payload)
        elif field_type == _KEYPOINTS_TYPE:
            fields[field_name] = _empty_keypoints_payload(field_payload)
        elif field_type == _POLYLINES_TYPE:
            fields[field_name] = _empty_polylines_payload(field_payload)

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
        if _MASK_FIELD in detection:
            instance_mask = _output_detection_mask(
                ref,
                detection,
                output_masks_by_ref,
                image_width=output_width,
                image_height=output_height,
            )
            if instance_mask is None:
                continue
            detection[_MASK_FIELD] = _mask_to_json(instance_mask)
            dropped["masks"] -= 1
        field = cast(dict[str, object], fields[ref.field_name])
        detections = cast(list[JSONDict], field["detections"])
        detections.append(normalize_json_mapping(detection))
        dropped["detections"] -= 1

    for raw_heatmap, ref in zip(
        _output_sequence(output_targets, _HEATMAPS_TARGET_FIELD),
        target_data.heatmap_refs,
        strict=False,
    ):
        source_field = _payload_fields(source_payload)[ref.field_name]
        if _payload_type(source_field) != _HEATMAP_TYPE:
            continue
        heatmap_payload: dict[str, object] = {
            **metadata_fields(source_field),
            _TYPE_FIELD: _HEATMAP_TYPE,
            _HEATMAP_MAP_FIELD: _heatmap_to_json(_heatmap_output_array(raw_heatmap)),
            "tags": _str_list(source_field.get("tags")),
        }
        _set_optional(heatmap_payload, "range", _float_sequence(source_field.get("range")))
        _set_optional(
            heatmap_payload,
            _HEATMAP_SOURCE_MAP_PATH_FIELD,
            _optional_str(source_field.get(_HEATMAP_MAP_PATH_FIELD)),
        )
        fields[ref.field_name] = normalize_json_mapping(heatmap_payload)
        dropped["heatmaps"] -= 1

    for raw_point, raw_ref_index in zip(
        _output_sequence(output_targets, "keypoints"),
        _output_sequence(output_targets, "keypoint_indices"),
        strict=False,
    ):
        ref = target_data.keypoint_refs[_target_index(raw_ref_index)]
        point = _absolute_point_to_relative(
            _float_sequence(raw_point), image_width=output_width, image_height=output_height
        )
        source_field = _payload_fields(source_payload)[ref.field_name]
        source_field_type = _payload_type(source_field)
        if source_field_type == _KEYPOINTS_TYPE:
            field = cast(dict[str, object], fields[ref.field_name])
            keypoints = cast(list[dict[str, object]], field["keypoints"])
            keypoint = keypoints[ref.label_index]
            assert ref.point_index is not None
            cast(list[JSONValue], keypoint["points"])[ref.point_index] = normalize_json_value(point)
            source_keypoint = _payload_sequence(source_field, "keypoints")[ref.label_index]
            if "visible" in source_keypoint:
                cast(list[JSONValue], keypoint["visible"])[ref.point_index] = _payload_sequence(
                    source_keypoint, "visible"
                )[ref.point_index]
            dropped["keypoints"] -= 1
        elif source_field_type == _POLYLINES_TYPE and ref.shape_index is not None:
            field = cast(dict[str, object], fields[ref.field_name])
            polylines = cast(list[dict[str, object]], field["polylines"])
            polyline = polylines[ref.label_index]
            shapes = cast(list[list[list[float]]], polyline["points"])
            shapes[ref.shape_index].append(point)
            dropped["polyline_points"] -= 1

    fields, dropped_polyline_shapes = _drop_empty_polylines(fields)
    if dropped_polyline_shapes:
        dropped["polyline_shapes"] = dropped_polyline_shapes

    for raw_mask, ref in zip(_output_sequence(output_targets, "masks"), target_data.mask_refs, strict=False):
        source_field = _payload_fields(source_payload)[ref.field_name]
        if _payload_type(source_field) != _SEGMENTATION_TYPE:
            continue
        segmentation_payload: dict[str, object] = {
            **metadata_fields(source_field),
            _TYPE_FIELD: _SEGMENTATION_TYPE,
            _MASK_FIELD: _mask_to_json(raw_mask),
            "tags": _str_list(source_field.get("tags")),
        }
        _set_optional(
            segmentation_payload,
            _SEGMENTATION_SOURCE_MASK_PATH_FIELD,
            _optional_str(source_field.get(_SEGMENTATION_MASK_PATH_FIELD)),
        )
        fields[ref.field_name] = normalize_json_mapping(segmentation_payload)
        dropped["masks"] -= 1

    metadata: JSONDict = {"dropped_annotations": {name: count for name, count in dropped.items() if count > 0}}
    if excluded_metadata:
        metadata["dropped_attributes"] = normalize_json_value(excluded_metadata)
    return {
        "fields": remove_geometry_metadata(normalize_json_mapping(fields), transformed_fields),
        "metadata": metadata,
    }


def _copy_static_fields(
    source_payload: Mapping[str, object],
    *,
    copy_label_fields: Sequence[str] = (),
) -> dict[str, JSONValue]:
    copied_field_names = set(str(field_name) for field_name in copy_label_fields)
    fields: dict[str, JSONValue] = {}
    for field_name, field_payload in _payload_fields(source_payload).items():
        field_type = _payload_type(field_payload)
        if field_type == _CLASSIFICATION_TYPE or field_name in copied_field_names:
            fields[field_name] = normalize_json_mapping(field_payload)
    return fields


def _empty_heatmap_payload(field_payload: Mapping[str, object]) -> JSONDict:
    payload: dict[str, object] = {
        **metadata_fields(field_payload),
        _TYPE_FIELD: _HEATMAP_TYPE,
        "tags": _str_list(field_payload.get("tags")),
    }
    _set_optional(payload, "range", _optional_heatmap_range(field_payload.get("range")))
    _set_optional(
        payload,
        _HEATMAP_SOURCE_MAP_PATH_FIELD,
        _optional_str(field_payload.get(_HEATMAP_MAP_PATH_FIELD)),
    )
    return normalize_json_mapping(payload)


def _empty_keypoints_payload(field_payload: Mapping[str, object]) -> JSONDict:
    keypoints = []
    for source_keypoint in _payload_sequence(field_payload, "keypoints"):
        keypoint = dict(source_keypoint)
        point_count = len(_payload_sequence(source_keypoint, "points"))
        keypoint["points"] = [None] * point_count
        if "visible" in keypoint:
            keypoint["visible"] = [0] * point_count
        keypoints.append(normalize_json_mapping(keypoint))
    return normalize_json_mapping(
        {**metadata_fields(field_payload), _TYPE_FIELD: _KEYPOINTS_TYPE, "keypoints": keypoints}
    )


def _empty_polylines_payload(field_payload: Mapping[str, object]) -> JSONDict:
    polylines = []
    for source_polyline in _payload_sequence(field_payload, "polylines"):
        polyline = dict(source_polyline)
        polyline["points"] = [[] for _shape in _payload_sequence(source_polyline, "points")]
        polylines.append(normalize_json_mapping(polyline))
    return normalize_json_mapping(
        {**metadata_fields(field_payload), _TYPE_FIELD: _POLYLINES_TYPE, "polylines": polylines}
    )


def _drop_empty_polylines(fields: Mapping[str, object]) -> tuple[dict[str, object], int]:
    updated = dict(fields)
    dropped_shapes = 0
    for field_name, field_payload in tuple(updated.items()):
        if not isinstance(field_payload, Mapping) or _payload_type(field_payload) != _POLYLINES_TYPE:
            continue
        polylines = []
        for source_polyline in _payload_sequence(field_payload, "polylines"):
            min_points = _polyline_min_points(source_polyline)
            shapes = []
            for shape in _payload_sequence(source_polyline, "points"):
                if len(_point_list(shape)) >= min_points:
                    shapes.append(shape)
                else:
                    dropped_shapes += 1
            if not shapes:
                continue
            polyline = dict(source_polyline)
            polyline["points"] = shapes
            polylines.append(normalize_json_mapping(polyline))
        updated[field_name] = {**metadata_fields(field_payload), _TYPE_FIELD: _POLYLINES_TYPE, "polylines": polylines}
    return updated, dropped_shapes


def _output_masks_by_ref(
    target_data: AnnotationTargets,
    output_targets: Mapping[str, object],
) -> dict[_AnnotationRef, npt.NDArray[Any]]:
    return {
        ref: np.asarray(raw_mask)
        for raw_mask, ref in zip(_output_sequence(output_targets, "masks"), target_data.mask_refs, strict=False)
    }


def _target_ref_count_by_field_type(
    refs: Sequence[_AnnotationRef],
    source_payload: Mapping[str, object],
    field_type: str,
) -> int:
    fields = _payload_fields(source_payload)
    return sum(1 for ref in refs if _payload_type(fields.get(ref.field_name, {})) == field_type)
