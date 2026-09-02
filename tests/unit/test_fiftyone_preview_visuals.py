from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from albumentationsx_plugin.hosts.fiftyone.augmentation.preview_visuals import (
    build_preview_visual_comparison,
)


@pytest.mark.unit
def test_preview_visual_comparison_renders_annotation_overlay_and_summary() -> None:
    source_image = _rgb_image(width=24, height=16)
    output_image = source_image[:, ::-1, :]
    source_labels: dict[str, Any] = {
        "fields": {
            "ground_truth": {"type": "classification", "label": "cat"},
            "detections": {
                "type": "detections",
                "detections": [
                    {
                        "label": "box",
                        "bounding_box": [0.1, 0.2, 0.3, 0.4],
                        "mask": [[1, 0, 1], [0, 1, 0]],
                    }
                ],
            },
            "keypoints": {
                "type": "keypoints",
                "keypoints": [{"label": "nose", "points": [[0.2, 0.3], [0.4, 0.5]]}],
            },
            "polylines": {
                "type": "polylines",
                "polylines": [{"label": "lane", "points": [[[0.2, 0.2], [0.6, 0.4], [0.7, 0.7]]]}],
            },
            "heatmap": {
                "type": "heatmap",
                "map": [[0.0, 0.2], [0.5, 1.0]],
            },
            "segmentation": {
                "type": "segmentation",
                "mask": [[0, 1, 1], [0, 0, 2]],
            },
            "dropped": {
                "type": "keypoints",
                "keypoints": [{"label": "outside", "points": [[0.9, 0.9]]}],
            },
        }
    }
    output_labels: dict[str, Any] = {
        "fields": {
            "ground_truth": {"type": "classification", "label": "cat"},
            "detections": {
                "type": "detections",
                "detections": [{"label": "box", "bounding_box": [0.6, 0.2, 0.3, 0.4]}],
            },
            "keypoints": {
                "type": "keypoints",
                "keypoints": [{"label": "nose", "points": [[0.8, 0.3], [0.6, 0.5]]}],
            },
            "polylines": {
                "type": "polylines",
                "polylines": [{"label": "lane", "points": [[[0.8, 0.2], [0.4, 0.4], [0.3, 0.7]]]}],
            },
            "heatmap": {
                "type": "heatmap",
                "map": [[0.2, 0.0], [1.0, 0.5]],
            },
            "segmentation": {
                "type": "segmentation",
                "mask": [[1, 1, 0], [2, 0, 0]],
            },
        },
        "metadata": {"dropped_annotations": {"keypoints": 1}},
    }

    comparison = build_preview_visual_comparison(
        source_image=source_image,
        output_image=output_image,
        source_labels=source_labels,
        output_labels=output_labels,
    )

    assert comparison.image.ndim == 3
    assert comparison.image.shape[2] == 3
    assert comparison.image.shape[0] > source_image.shape[0]
    assert comparison.image.shape[1] > source_image.shape[1] * 2
    assert np.any(comparison.image != 0)

    rows = _rows_by_field(comparison.annotation_comparison)
    assert rows["ground_truth"]["status"] == "copied"
    assert rows["ground_truth"]["rendered_overlay"] is False
    assert rows["detections"]["status"] == "transformed"
    assert rows["detections"]["rendered_overlay"] is True
    assert rows["keypoints"]["source_geometry_count"] == 2
    assert rows["keypoints"]["output_geometry_count"] == 2
    assert rows["dropped"]["status"] == "dropped"
    assert comparison.annotation_comparison["dropped_annotations"] == {"keypoints": 1}


@pytest.mark.unit
def test_preview_visual_comparison_handles_empty_annotation_payloads() -> None:
    source_image = _rgb_image(width=8, height=6)

    comparison = build_preview_visual_comparison(
        source_image=source_image,
        output_image=source_image,
        source_labels={},
        output_labels={},
    )

    assert comparison.image.shape[2] == 3
    assert comparison.annotation_comparison == {
        "fields": [],
        "totals": {
            "output_annotations": 0,
            "output_geometry": 0,
            "source_annotations": 0,
            "source_geometry": 0,
        },
        "dropped_annotations": {},
    }


def _rgb_image(*, width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None]
    image[..., 2] = 90
    return image


def _rows_by_field(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload["fields"]
    assert isinstance(rows, list)
    return {str(row["field_name"]): cast(dict[str, Any], row) for row in rows if isinstance(row, dict)}
