from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config, create_fixed_image_pipeline
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    annotation_payload_from_sample,
    labels_from_annotation_payload,
    target_data_from_annotation_payload,
    transformed_annotation_payload,
)

pytestmark = pytest.mark.unit


def _round_trip(label: fo.Label) -> tuple[dict[str, Any], Any]:
    payload = annotation_payload_from_sample(fo.Sample(filepath="/unused.png", ground_truth=label), ("ground_truth",))
    payload = json.loads(json.dumps(payload, allow_nan=False))
    return payload, labels_from_annotation_payload(payload)["ground_truth"]


@pytest.mark.parametrize("kind", ["classification", "detections", "keypoints", "polylines", "segmentation", "heatmap"])
def test_supported_label_families_preserve_dynamic_and_container_metadata(kind: str) -> None:
    labels: dict[str, fo.Label] = {
        "classification": fo.Classification(label="person"),
        "detections": fo.Detections(
            detections=[
                fo.Detection(label="phone", bounding_box=[0.1, 0.2, 0.3, 0.4], iscrowd=0, supercategory="electronic")
            ]
        ),
        "keypoints": fo.Keypoints(
            keypoints=[
                fo.Keypoint(
                    points=[(0.2, 0.3), (np.nan, np.nan)],
                    visible=[2, 0],
                    joint_names=["nose", "eye"],
                    quality=[0.9, 0.5],
                )
            ]
        ),
        "polylines": fo.Polylines(polylines=[fo.Polyline(points=[[(0.1, 0.2), (0.4, 0.5)]], road_type="lane")]),
        "segmentation": fo.Segmentation(mask=np.ones((4, 5), dtype=np.uint8)),
        "heatmap": fo.Heatmap(map=np.ones((4, 5), dtype=np.float32)),
    }
    label = labels[kind]
    label["source"] = "manual"
    label["review"] = {"approved": True, "scores": [1, 2.5, None], "notes": {"text": "проверено"}}
    label["measurements"] = np.asarray([0.5, 1.0], dtype=np.float32)
    label["type"] = "user-type"
    label["custom_fields"] = {"user": "value"}
    label["attributes"] = {"user": "dynamic field named attributes"}
    label["tags"] = ["checked"]
    _, restored = _round_trip(label)
    assert restored["source"] == "manual"
    assert restored["review"] == label["review"]
    assert restored["measurements"] == [0.5, 1.0]
    assert restored["type"] == "user-type"
    assert restored["custom_fields"] == {"user": "value"}
    assert restored["attributes"] == {"user": "dynamic field named attributes"}
    assert restored["tags"] == ["checked"]
    if kind == "detections":
        assert restored.detections[0].iscrowd == 0
        assert restored.detections[0].supercategory == "electronic"
        assert restored.detections[0].id != cast(Any, label).detections[0].id
    if kind == "keypoints":
        assert restored.keypoints[0].joint_names == ["nose", "eye"]
        assert restored.keypoints[0].quality == [0.9, 0.5]
        assert restored.keypoints[0].visible == [2, 0]
    if kind == "polylines":
        assert restored.polylines[0].road_type == "lane"


def test_legacy_attributes_preserve_values_types_and_attribute_metadata() -> None:
    label = fo.Detections(
        detections=[
            fo.Detection(
                bounding_box=[0.1, 0.2, 0.3, 0.4],
                attributes={
                    "class": fo.CategoricalAttribute(value="phone", confidence=0.8, logits=[0.2, 0.8]),
                    "list": fo.ListAttribute(value=[1, "two", {"three": True}]),
                    "dict": fo.Attribute(value={"reviewed": True}),
                    "same_name": fo.CategoricalAttribute(value="legacy"),
                },
                same_name="dynamic",
            )
        ]
    )
    _, restored = _round_trip(label)
    detection = restored.detections[0]
    assert detection.same_name == "dynamic"
    assert detection.attributes["same_name"].value == "legacy"
    assert detection.attributes["class"].confidence == 0.8
    np.testing.assert_allclose(detection.attributes["class"].logits, [0.2, 0.8])
    assert isinstance(detection.attributes["list"], fo.ListAttribute)
    assert detection.attributes["list"].value == [1, "two", {"three": True}]
    assert detection.attributes["dict"].value == {"reviewed": True}


@pytest.mark.geometry
def test_geometry_exclusions_are_explicit_and_do_not_change_source_metadata() -> None:
    detection = fo.Detection(
        label="phone",
        bounding_box=[0.1, 0.2, 0.3, 0.4],
        area=120,
        iscrowd=0,
        supercategory="electronic",
        reviewed_at=datetime(2026, 1, 1),
        attributes={"area": fo.NumericAttribute(value=120)},
    )
    payload = annotation_payload_from_sample(
        fo.Sample(filepath="/unused.png", detections=fo.Detections(detections=[detection])), ("detections",)
    )
    targets = target_data_from_annotation_payload(payload, (8, 10, 3))
    pipeline = create_fixed_image_pipeline(build_fixed_pipeline_config({"transform": "HorizontalFlip", "p": 1.0}))
    result = pipeline.apply(np.zeros((8, 10, 3), dtype=np.uint8), targets=targets.values)
    transformed = transformed_annotation_payload(payload, targets, result.targets, result.image.shape)
    output = cast(Any, labels_from_annotation_payload(transformed)["detections"]).detections[0]
    assert output.bounding_box == pytest.approx([0.6, 0.2, 0.3, 0.4])
    assert output.iscrowd == 0 and output.supercategory == "electronic"
    assert not output.has_field("area") and not output.has_field("reviewed_at")
    assert "area" not in output.attributes
    exclusions = cast(dict[str, Any], transformed["metadata"])["dropped_attributes"]
    assert {item["field_path"] for item in exclusions} == {
        "detections.detections[0].area",
        "detections.detections[0].attributes.area",
        "detections.detections[0].reviewed_at",
    }
    assert detection["area"] == 120 and detection["reviewed_at"] == datetime(2026, 1, 1)
    assert detection.attributes["area"].value == 120
    round_trip = cast(Any, labels_from_annotation_payload(payload)["detections"]).detections[0]
    assert round_trip.area == 120


def test_copied_geometry_keeps_derived_attributes() -> None:
    payload, _ = _round_trip(fo.Detections(detections=[fo.Detection(bounding_box=[0.1, 0.2, 0.3, 0.4], area=120)]))
    targets = target_data_from_annotation_payload(payload, (8, 10, 3), label_fields=())
    copied = transformed_annotation_payload(payload, targets, {}, (8, 10, 3), copy_label_fields=("ground_truth",))
    output = cast(Any, labels_from_annotation_payload(copied)["ground_truth"]).detections[0]
    assert output.area == 120


def test_reserved_custom_metadata_cannot_overwrite_label_geometry() -> None:
    payload = {
        "fields": {
            "d": {
                "type": "detections",
                "detections": [{"bounding_box": [0.1, 0.2, 0.3, 0.4], "custom_fields": {"bounding_box": [0, 0, 1, 1]}}],
            }
        }
    }
    with pytest.raises(ValueError, match="Reserved custom label field"):
        labels_from_annotation_payload(payload)


def test_non_json_custom_values_are_reported_without_stringification() -> None:
    label = fo.Detections(
        detections=[
            fo.Detection(
                bounding_box=[0.1, 0.2, 0.3, 0.4],
                review={"score": float("nan")},
                attributes={"reviewed_at": fo.Attribute(value=datetime(2026, 1, 1))},
            )
        ]
    )
    payload, restored = _round_trip(label)
    assert not restored.detections[0].has_field("review")
    assert "reviewed_at" not in restored.detections[0].attributes
    exclusions = payload["fields"]["ground_truth"]["detections"][0]["metadata_exclusions"]
    assert {item["name"] for item in exclusions} == {"review", "attributes.reviewed_at"}
