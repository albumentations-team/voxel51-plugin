from __future__ import annotations

from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest
from PIL import Image

from albumentationsx_plugin.hosts.fiftyone.annotations import (
    annotation_payload_from_sample,
    labels_from_annotation_payload,
    target_data_from_annotation_payload,
    transformed_annotation_payload,
)
from albumentationsx_plugin.storage.images import write_mask_image


def _detection_instance_mask() -> np.ndarray:
    return np.asarray(
        [
            [1, 0],
            [1, 1],
            [0, 1],
            [1, 1],
        ],
        dtype=np.uint8,
    )


@pytest.mark.unit
def test_detection_instance_mask_round_trips_through_full_image_mask_target() -> None:
    source_payload: dict[str, object] = {
        "fields": {
            "detections": {
                "type": "detections",
                "detections": [
                    {
                        "label": "object",
                        "bounding_box": [0.1, 0.25, 0.2, 0.5],
                        "mask": _detection_instance_mask().tolist(),
                    }
                ],
            }
        }
    }

    target_data = target_data_from_annotation_payload(source_payload, image_shape=(8, 10, 3))
    target_masks = cast(np.ndarray, target_data.values["masks"])

    assert target_masks.shape == (1, 8, 10)
    np.testing.assert_array_equal(target_masks[0, 2:6, 1:3], _detection_instance_mask())

    transformed_payload = transformed_annotation_payload(
        source_payload,
        target_data,
        {
            "bboxes": [[7.0, 2.0, 9.0, 6.0]],
            "bbox_indices": [0],
            "masks": target_masks[:, :, ::-1],
        },
        output_shape=(8, 10, 3),
    )

    fields = cast(dict[str, Any], transformed_payload["fields"])
    output_detection = cast(list[dict[str, Any]], fields["detections"]["detections"])[0]

    assert output_detection["bounding_box"] == pytest.approx([0.7, 0.25, 0.2, 0.5])
    np.testing.assert_array_equal(
        np.asarray(output_detection["mask"], dtype=np.uint8),
        _detection_instance_mask()[:, ::-1],
    )

    labels = labels_from_annotation_payload(transformed_payload)
    detection_label = cast(Any, labels["detections"]).detections[0]
    np.testing.assert_array_equal(np.asarray(detection_label.mask), _detection_instance_mask()[:, ::-1])


@pytest.mark.unit
def test_detection_mask_path_is_serialized_as_instance_mask(tmp_path) -> None:
    mask_path = write_mask_image(_detection_instance_mask(), tmp_path, "masks/detection.png")
    sample = fo.Sample(
        filepath=str(tmp_path / "source.png"),
        detections=fo.Detections(
            detections=[
                fo.Detection(
                    label="object",
                    bounding_box=[0.1, 0.25, 0.2, 0.5],
                    mask_path=str(mask_path),
                )
            ]
        ),
    )

    payload = annotation_payload_from_sample(sample, ("detections",))
    fields = cast(dict[str, Any], payload["fields"])
    detection_payload = cast(list[dict[str, Any]], fields["detections"]["detections"])[0]

    np.testing.assert_array_equal(np.asarray(detection_payload["mask"], dtype=np.uint8), _detection_instance_mask())


@pytest.mark.unit
def test_heatmap_round_trips_through_image_sequence_target() -> None:
    source_map = np.asarray(
        [
            [0.0, 0.5, 1.0],
            [0.25, 0.75, 0.5],
        ],
        dtype=np.float32,
    )
    source_payload: dict[str, object] = {
        "fields": {
            "heatmap": {
                "type": "heatmap",
                "map": source_map.tolist(),
                "range": [0.0, 1.0],
                "tags": ["soft-target"],
            }
        }
    }

    target_data = target_data_from_annotation_payload(source_payload, image_shape=(2, 3, 3))
    target_heatmaps = cast(np.ndarray, target_data.values["heatmaps"])

    assert target_heatmaps.shape == (1, 2, 3, 1)
    np.testing.assert_allclose(target_heatmaps[0, :, :, 0], source_map)

    output_map = source_map[:, ::-1]
    transformed_payload = transformed_annotation_payload(
        source_payload,
        target_data,
        {"heatmaps": output_map[np.newaxis, :, :, np.newaxis]},
        output_shape=(2, 3, 3),
    )

    fields = cast(dict[str, Any], transformed_payload["fields"])
    heatmap_payload = cast(dict[str, Any], fields["heatmap"])
    assert heatmap_payload["range"] == [0.0, 1.0]
    assert heatmap_payload["tags"] == ["soft-target"]
    np.testing.assert_allclose(np.asarray(heatmap_payload["map"], dtype=np.float32), output_map)

    labels = labels_from_annotation_payload(transformed_payload)
    heatmap_label = cast(fo.Heatmap, labels["heatmap"])
    assert heatmap_label.range == [0.0, 1.0]
    assert heatmap_label.tags == ["soft-target"]
    np.testing.assert_allclose(np.asarray(heatmap_label.map, dtype=np.float32), output_map)


@pytest.mark.unit
def test_heatmap_map_path_is_serialized_and_preserved_when_copied(tmp_path) -> None:
    heatmap_image = np.asarray([[0, 128], [255, 32]], dtype=np.uint8)
    heatmap_path = tmp_path / "heatmap.png"
    Image.fromarray(heatmap_image).save(heatmap_path)
    sample = fo.Sample(
        filepath=str(tmp_path / "source.png"),
        heatmap=fo.Heatmap(map_path=str(heatmap_path), range=[0, 255]),
    )

    payload = annotation_payload_from_sample(sample, ("heatmap",))
    fields = cast(dict[str, Any], payload["fields"])
    heatmap_payload = cast(dict[str, Any], fields["heatmap"])

    assert heatmap_payload["map_path"] == str(heatmap_path)
    assert heatmap_payload["range"] == [0.0, 255.0]
    np.testing.assert_array_equal(np.asarray(heatmap_payload["map"], dtype=np.uint8), heatmap_image)

    labels = labels_from_annotation_payload(payload)
    heatmap_label = cast(fo.Heatmap, labels["heatmap"])
    assert heatmap_label.map_path == str(heatmap_path)
    assert heatmap_label.map is None


@pytest.mark.unit
def test_polyline_round_trips_through_keypoint_targets() -> None:
    source_payload: dict[str, object] = {
        "fields": {
            "polylines": {
                "type": "polylines",
                "polylines": [
                    {
                        "label": "lane",
                        "points": [
                            [[0.1, 0.25], [0.3, 0.25], [0.3, 0.5]],
                            [[0.4, 0.5], [0.5, 0.625], [0.6, 0.5]],
                        ],
                        "confidence": 0.7,
                        "tags": ["annotated"],
                        "attributes": {"source": "manual"},
                        "index": 3,
                        "closed": True,
                        "filled": True,
                    }
                ],
            }
        }
    }

    target_data = target_data_from_annotation_payload(source_payload, image_shape=(8, 10, 3))

    np.testing.assert_allclose(
        np.asarray(target_data.values["keypoints"], dtype=np.float32),
        np.asarray(
            [
                [1.0, 2.0],
                [3.0, 2.0],
                [3.0, 4.0],
                [4.0, 4.0],
                [5.0, 5.0],
                [6.0, 4.0],
            ],
            dtype=np.float32,
        ),
    )

    transformed_payload = transformed_annotation_payload(
        source_payload,
        target_data,
        {
            "keypoints": [
                [8.0, 2.0],
                [6.0, 2.0],
                [6.0, 4.0],
                [5.0, 4.0],
                [4.0, 5.0],
                [3.0, 4.0],
            ],
            "keypoint_indices": [0, 1, 2, 3, 4, 5],
        },
        output_shape=(8, 10, 3),
    )

    fields = cast(dict[str, Any], transformed_payload["fields"])
    output_polyline = cast(list[dict[str, Any]], fields["polylines"]["polylines"])[0]

    assert output_polyline["label"] == "lane"
    assert output_polyline["confidence"] == pytest.approx(0.7)
    assert output_polyline["tags"] == ["annotated"]
    assert output_polyline["attributes"] == {"source": "manual"}
    assert output_polyline["index"] == 3
    assert output_polyline["closed"] is True
    assert output_polyline["filled"] is True
    expected_points = [
        [[0.8, 0.25], [0.6, 0.25], [0.6, 0.5]],
        [[0.5, 0.5], [0.4, 0.625], [0.3, 0.5]],
    ]
    for output_shape, expected_shape in zip(output_polyline["points"], expected_points, strict=True):
        np.testing.assert_allclose(
            np.asarray(output_shape, dtype=np.float32),
            np.asarray(expected_shape, dtype=np.float32),
        )

    labels = labels_from_annotation_payload(transformed_payload)
    polyline_label = cast(Any, labels["polylines"]).polylines[0]
    assert polyline_label.label == "lane"
    assert polyline_label.confidence == pytest.approx(0.7)
    assert polyline_label.attributes["source"].value == "manual"
    assert polyline_label.index == 3
    assert polyline_label.closed is True
    assert polyline_label.filled is True
    for output_shape, expected_shape in zip(polyline_label.points, expected_points, strict=True):
        np.testing.assert_allclose(
            np.asarray(output_shape, dtype=np.float32),
            np.asarray(expected_shape, dtype=np.float32),
        )


@pytest.mark.unit
def test_polyline_shapes_with_too_few_visible_points_are_dropped() -> None:
    source_payload: dict[str, object] = {
        "fields": {
            "polylines": {
                "type": "polylines",
                "polylines": [
                    {
                        "label": "crop-edge",
                        "points": [[[0.1, 0.25], [0.3, 0.25]]],
                        "closed": False,
                        "filled": False,
                    },
                    {
                        "label": "polygon-edge",
                        "points": [[[0.4, 0.5], [0.5, 0.625], [0.6, 0.5]]],
                        "closed": True,
                        "filled": True,
                    },
                ],
            }
        }
    }
    target_data = target_data_from_annotation_payload(source_payload, image_shape=(8, 10, 3))

    transformed_payload = transformed_annotation_payload(
        source_payload,
        target_data,
        {
            "keypoints": [
                [1.0, 2.0],
                [4.0, 4.0],
                [5.0, 5.0],
            ],
            "keypoint_indices": [0, 2, 3],
        },
        output_shape=(8, 10, 3),
    )

    fields = cast(dict[str, Any], transformed_payload["fields"])
    assert fields["polylines"] == {"type": "polylines", "polylines": []}
    assert transformed_payload["metadata"] == {
        "dropped_annotations": {
            "polyline_points": 2,
            "polyline_shapes": 2,
        }
    }
