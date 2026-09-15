from __future__ import annotations

import json
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import (
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
)
from albumentationsx_plugin.core import HostAdapterError
from albumentationsx_plugin.core.serialization import normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    annotation_payload_from_sample,
    labels_from_annotation_payload,
    target_data_from_annotation_payload,
    transformed_annotation_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.geometry]


def _sample(*keypoints: fo.Keypoint) -> fo.Sample:
    return fo.Sample(filepath="/unused/source.png", pose=fo.Keypoints(keypoints=list(keypoints)))


def _transform(sample: fo.Sample, params: dict[str, object]) -> tuple[dict[str, Any], Any]:
    payload = annotation_payload_from_sample(sample, ("pose",))
    # Exercise the actual JSON boundary, not Python's permissive NaN encoder.
    payload = json.loads(json.dumps(payload, allow_nan=False))
    targets = target_data_from_annotation_payload(payload, (8, 10, 3))
    assert np.isfinite(np.asarray(targets.values.get("keypoints", []))).all()
    pipeline = create_fixed_image_pipeline(build_fixed_pipeline_config(params))
    result = pipeline.apply(np.zeros((8, 10, 3), dtype=np.uint8), targets=targets.values)
    transformed = transformed_annotation_payload(payload, targets, result.targets, result.image.shape)
    transformed = json.loads(json.dumps(transformed, allow_nan=False))
    return transformed, cast(fo.Keypoints, labels_from_annotation_payload(transformed)["pose"])


def test_flip_preserves_missing_slots_people_visibility_and_confidence() -> None:
    sample = _sample(
        fo.Keypoint(
            label="person",
            index=7,
            points=[(0.2, 0.25), (float("nan"), float("nan")), (0.6, 0.5)],
            visible=[2, 0, 1],
            confidence=[0.9, 0.0, 0.7],
            tags=["pose"],
        ),
        fo.Keypoint(label="person", index=8, points=[(float("nan"), float("nan"))] * 3, visible=[0, 0, 0]),
        fo.Keypoint(label="person", index=9, points=[(0.4, 0.75)], visible=[2], confidence=[0.8]),
    )
    before = np.asarray(sample.pose.keypoints[0].points).copy()
    payload, labels = _transform(sample, {"transform": "HorizontalFlip", "p": 1.0})
    first, missing, last = labels.keypoints
    np.testing.assert_allclose(first.points, [(0.7, 0.25), (np.nan, np.nan), (0.3, 0.5)], equal_nan=True)
    assert first.visible == [2, 0, 1]
    assert first.confidence == [0.9, 0.0, 0.7]
    assert first.tags == ["pose"]
    assert [kp.index for kp in labels.keypoints] == [7, 8, 9]
    assert np.isnan(np.asarray(missing.points)).all()
    assert len(missing.points) == 3
    assert missing.visible == [0, 0, 0]
    assert last.points[0] == pytest.approx([0.5, 0.75])
    assert last.confidence == [0.8]
    assert payload["fields"]["pose"]["keypoints"][0]["points"][1] is None
    assert payload["metadata"]["dropped_annotations"] == {}
    np.testing.assert_allclose(sample.pose.keypoints[0].points, before, equal_nan=True)


@pytest.mark.parametrize("entirely_missing", [True, False])
def test_crop_retains_anatomical_slots_and_counts_only_newly_lost_points(entirely_missing: bool) -> None:
    points = [(0.1, 0.25), (np.nan, np.nan), (0.7, 0.5)]
    if entirely_missing:
        points[2] = (0.2, 0.5)
    sample = _sample(fo.Keypoint(points=points, visible=[2, 0, 1], confidence=[0.9, 0.0, 0.7]))
    payload, labels = _transform(
        sample, {"transform": "Crop", "x_min": 5, "y_min": 0, "x_max": 10, "y_max": 8, "p": 1.0}
    )
    kp = labels.keypoints[0]
    assert len(kp.points) == 3
    assert np.isnan(np.asarray(kp.points[:2])).all()
    assert kp.confidence == [0.9, 0.0, 0.7]
    assert kp.visible == ([0, 0, 0] if entirely_missing else [0, 0, 1])
    if entirely_missing:
        assert np.isnan(np.asarray(kp.points)).all()
    else:
        assert kp.points[2] == pytest.approx([0.4, 0.5])
    assert payload["metadata"]["dropped_annotations"] == {"keypoints": 2 if entirely_missing else 1}


def test_all_missing_keypoints_need_no_runtime_coordinates() -> None:
    sample = _sample(fo.Keypoint(points=[(np.nan, np.nan)] * 17, visible=[0] * 17))
    payload, labels = _transform(sample, {"transform": "HorizontalFlip", "p": 1.0})
    assert payload["fields"]["pose"]["keypoints"][0]["points"] == [None] * 17
    assert len(labels.keypoints[0].points) == 17
    assert np.isnan(np.asarray(labels.keypoints[0].points)).all()


def test_copied_keypoints_keep_missing_slots_and_metadata() -> None:
    sample = _sample(fo.Keypoint(points=[(0.2, 0.5), (np.nan, np.nan)], confidence=[0.9, 0], visible=[1, 0]))
    payload = annotation_payload_from_sample(sample, ("pose",))
    targets = target_data_from_annotation_payload(payload, (8, 10, 3), label_fields=())
    assert targets.values == {}
    copied = transformed_annotation_payload(payload, targets, {}, (8, 10, 3), copy_label_fields=("pose",))
    assert copied["fields"] == payload["fields"]
    labels = cast(Any, labels_from_annotation_payload(copied)["pose"])
    np.testing.assert_allclose(labels.keypoints[0].points, sample.pose.keypoints[0].points, equal_nan=True)
    assert labels.keypoints[0].visible == [1, 0]
    assert labels.keypoints[0].confidence == [0.9, 0]


def test_normalized_boundary_points_are_accepted() -> None:
    sample = _sample(fo.Keypoint(points=[(0, 0), (1, 1)]))
    _, labels = _transform(sample, {"transform": "HorizontalFlip", "p": 1.0})
    np.testing.assert_allclose(labels.keypoints[0].points, [(0.9, 0), (0, 0.875)], atol=1e-6)


@pytest.mark.parametrize("point", [(np.inf, 0.5), (np.nan, 0.5), (-0.1, 0.5)])
def test_invalid_point_has_sample_field_and_point_diagnostic(point: tuple[float, float]) -> None:
    sample = _sample(fo.Keypoint(points=[point]))
    with pytest.raises(HostAdapterError) as caught:
        annotation_payload_from_sample(sample, ("pose",))
    assert caught.value.context["field_name"] == "pose"
    assert caught.value.context["sample_id"] == str(sample.id)
    assert "keypoint 0" in caught.value.message.lower()
    assert "point 0" in caught.value.message.lower()
    assert "deselect" in caught.value.message.lower()
    json.dumps(caught.value.to_dict(), allow_nan=False)


@pytest.mark.parametrize("field,value", [("confidence", [float("nan")]), ("visible", [2, 1])])
def test_invalid_per_point_metadata_is_reported(field: str, value: list[float]) -> None:
    sample = _sample(fo.Keypoint(points=[(0.2, 0.5)], **{field: value}))
    with pytest.raises(HostAdapterError, match=field):
        annotation_payload_from_sample(sample, ("pose",))


def test_non_keypoint_nan_still_fails_strict_serialization() -> None:
    with pytest.raises(TypeError, match="NaN"):
        normalize_json_value({"unrelated": float("nan")})
    sample = fo.Sample(filepath="/unused/source.png", prediction=fo.Classification(label="person", confidence=np.inf))
    with pytest.raises(HostAdapterError):
        annotation_payload_from_sample(sample, ("prediction",))
