from __future__ import annotations

from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

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
