from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import fiftyone as fo
import numpy as np
import pytest
from fiftyone.utils.coco import COCOObject

from albumentationsx_plugin.hosts.fiftyone.annotations import SELECTED_LABEL_FIELDS_PARAM_NAME
from albumentationsx_plugin.hosts.fiftyone.diagnostics import DEBUG_BUNDLE_FIELD_NAME
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
from albumentationsx_plugin.hosts.fiftyone.presets import STORAGE_ROOT_PARAM_NAME
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    PREVIEW_FIELD_LABELS_JSON,
    PREVIEW_ONLY_FIELD_NAME,
    preview_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import cleanup_run
from albumentationsx_plugin.hosts.fiftyone.samples import SOURCE_SAMPLE_ID_FIELD
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = [pytest.mark.integration, pytest.mark.geometry]


def test_coco_missing_keypoints_through_operator_preview_dry_run_and_materialization(tmp_path: Path) -> None:
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/coco_keypoints_48564.json").read_text())
    width, height = fixture["image"]["width"], fixture["image"]["height"]
    # Real COCO annotation/importer, deterministic local media; no download or pycocotools dependency.
    pose = COCOObject(**fixture["annotation"]).to_keypoints((width, height), classes_map={1: "person"})
    assert pose is not None
    pose.confidence = [i / 20 for i in range(17)]
    source_points = np.asarray(pose.points).copy()
    missing = np.isnan(source_points[:, 0])
    assert missing.sum() == 7
    original_visible = list(pose["visible"])
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, : width // 2, 0] = 255
    source_path = write_rgb_image(image, tmp_path, "sources/coco-pose.png")
    source_bytes = source_path.read_bytes()
    dataset = fo.Dataset(f"vox-68-coco-{uuid.uuid4().hex}")
    storage_root = tmp_path / "runs"
    try:
        source_id = dataset.add_sample(
            fo.Sample(
                filepath=str(source_path),
                metadata=fo.ImageMetadata(width=width, height=height),
                keypoints=fo.Keypoints(keypoints=[pose]),
                detections=fo.Detections(detections=[fo.Detection(label="person", bounding_box=[0.1, 0.2, 0.3, 0.4])]),
                segmentations=fo.Detections(
                    detections=[
                        fo.Detection(
                            label="person", bounding_box=[0.1, 0.2, 0.3, 0.4], mask=np.ones((4, 3), dtype=bool)
                        )
                    ]
                ),
            )
        )
        missing_id = dataset.add_sample(
            fo.Sample(
                filepath=str(source_path),
                keypoints=fo.Keypoints(keypoints=[fo.Keypoint(points=[(np.nan, np.nan)] * 17, visible=[0] * 17)]),
            )
        )
        empty_id = dataset.add_sample(fo.Sample(filepath=str(source_path)))
        source_ids = (source_id, missing_id, empty_id)
        params: dict[str, object] = {
            "transform": "HorizontalFlip",
            "p": 1.0,
            "outputs_per_sample": 1,
            SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections", "segmentations", "keypoints"],
            STORAGE_ROOT_PARAM_NAME: str(storage_root),
        }
        ctx = SimpleNamespace(
            dataset=dataset, view=dataset, selected=source_ids, params=params, trigger=Mock(), set_progress=Mock()
        )
        operator = AugmentWithAlbumentationsX()
        ctx.params = {**params, PREVIEW_ONLY_FIELD_NAME: True}
        preview = operator.execute(ctx)
        assert preview["error_count"] == 0, preview
        assert preview["preview_count"] == 3
        preview_labels = json.loads(str(preview[preview_field_name(1, PREVIEW_FIELD_LABELS_JSON)]))
        preview_pose = preview_labels["fields"]["keypoints"]["keypoints"][0]
        assert len(preview_pose["points"]) == 17
        assert [p is None for p in preview_pose["points"]] == missing.tolist()
        assert preview_pose["visible"] == original_visible
        assert preview_pose["confidence"] == pose.confidence
        json.dumps(preview_labels, allow_nan=False)
        assert not storage_root.exists()

        ctx.params = {**params, "dry_run": True}
        dry_run = operator.execute(ctx)
        assert dry_run["error_count"] == 0, dry_run
        assert dry_run["processed_count"] == 3
        assert dry_run["created_count"] == 0
        assert len(dataset) == 3
        assert dataset.list_runs() == []
        assert not storage_root.exists()
        ctx.trigger.assert_not_called()

        ctx.params = params
        result = operator.execute(ctx)
        assert result["error_count"] == 0, result
        assert result["created_count"] == 3
        ctx.trigger.assert_called_once_with("reload_dataset")
        outputs = {sample[SOURCE_SAMPLE_ID_FIELD]: sample for sample in dataset.exists(SOURCE_SAMPLE_ID_FIELD)}
        transformed_pose = outputs[source_id].keypoints.keypoints[0]
        expected = source_points.copy()
        expected[~missing, 0] = (width - 1 - expected[~missing, 0] * width) / width
        np.testing.assert_allclose(transformed_pose.points, expected, atol=1e-6, equal_nan=True)
        assert transformed_pose.visible == original_visible
        assert transformed_pose.confidence == pose.confidence
        for index in np.flatnonzero(~missing):
            assert transformed_pose.points[index] == pytest.approx(preview_pose["points"][index])
        assert len(outputs[source_id].detections.detections) == 1
        assert outputs[source_id].segmentations.detections[0].mask is not None
        assert len(outputs[missing_id].keypoints.keypoints[0].points) == 17
        assert np.isnan(np.asarray(outputs[missing_id].keypoints.keypoints[0].points)).all()
        assert outputs[empty_id].keypoints is None

        saved_source = cast(Any, dataset[source_id])
        np.testing.assert_allclose(saved_source.keypoints.keypoints[0].points, source_points, equal_nan=True)
        assert saved_source.keypoints.keypoints[0].visible == original_visible
        assert source_path.read_bytes() == source_bytes
        manifest = FileRunStore(dataset.name, storage_root=storage_root).load_manifest(str(result["run_key"]))
        json.dumps(manifest.to_dict(), allow_nan=False)
        cleanup_run(
            dataset=cast(Any, dataset), run_key=str(result["run_key"]), storage_root=storage_root, confirmed=True
        )
        assert len(dataset) == 3
        assert source_path.read_bytes() == source_bytes

        # Invalid coordinates remain a precise preflight error, without partial writes.
        invalid = cast(Any, dataset[source_id])
        invalid.keypoints.keypoints[0].points[2] = (float("inf"), 0.5)
        invalid.save()
        for mode in ({PREVIEW_ONLY_FIELD_NAME: True}, {"dry_run": True}, {}):
            ctx.params = {**params, **mode}
            failed = operator.execute(ctx)
            assert failed["error_count"] == 1
            errors = cast(list[dict[str, Any]], failed["errors"])
            assert errors[0]["code"] == "host_adapter_error"
            assert errors[0]["context"]["sample_id"] == source_id
            assert errors[0]["context"]["field_name"] == "keypoints"
            assert errors[0]["context"]["reason"] == "invalid_annotation_data"
            assert "Point 2" in errors[0]["message"]
            bundle = json.loads(str(failed[DEBUG_BUNDLE_FIELD_NAME]))
            assert any("deselect" in step for step in bundle["suggested_next_steps"])
            assert len(dataset) == 3
    finally:
        dataset.delete()
