from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import fiftyone as fo
import numpy as np
import pytest
from fiftyone.utils.coco import COCOObject

from albumentationsx_plugin.hosts.fiftyone.annotations import SELECTED_LABEL_FIELDS_PARAM_NAME
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
from albumentationsx_plugin.hosts.fiftyone.output_metadata import OUTPUT_METADATA_POLICY
from albumentationsx_plugin.hosts.fiftyone.presets import STORAGE_ROOT_PARAM_NAME
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON,
    PREVIEW_FIELD_LABELS_JSON,
    PREVIEW_ONLY_FIELD_NAME,
    preview_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import cleanup_run
from albumentationsx_plugin.hosts.fiftyone.samples import SOURCE_SAMPLE_ID_FIELD
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = [pytest.mark.integration, pytest.mark.geometry]


def test_output_metadata_policy_and_preservation_across_execution_modes(tmp_path: Path) -> None:
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/coco_detection_48564.json").read_text())
    width, height = fixture["image"]["width"], fixture["image"]["height"]
    category = fixture["category"]
    # Real COCO importer attributes, with additional user metadata and offline media.
    detection = COCOObject(**fixture["annotation"]).to_detection(
        (width, height),
        classes_map={category["id"]: category["name"]},
        supercategory_map={category["name"]: category},
        include_id=True,
    )
    assert detection is not None
    detection["review"] = {"accepted": True, "scores": [0.8, 0.9]}
    detection["area"] = fixture["annotation"]["area"]
    detection["reviewed_at"] = datetime(2026, 1, 1)
    detection.tags = ["verified"]
    detection.attributes["quality"] = fo.NumericAttribute(value=0.95)
    source_path = write_rgb_image(np.zeros((height, width, 3), dtype=np.uint8), tmp_path, "source.png")
    source_bytes = source_path.read_bytes()
    dataset = fo.Dataset(f"output-metadata-{uuid.uuid4().hex}")
    storage_root = tmp_path / "runs"
    try:
        source_id = dataset.add_sample(
            fo.Sample(
                filepath=str(source_path),
                metadata=fo.ImageMetadata(width=width, height=height),
                tags=["validation", "user-tag"],
                coco_id=fixture["image"]["id"],
                reviewer="alice",
                detections=fo.Detections(detections=[detection], origin="manual", tags=["reviewed-container"]),
                ignored=fo.Classification(label="do not copy"),
            )
        )
        original_json = json.loads(dataset[source_id].to_json())
        params: dict[str, object] = {
            "transform": "HorizontalFlip",
            "p": 1.0,
            "outputs_per_sample": 1,
            SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections"],
            STORAGE_ROOT_PARAM_NAME: str(storage_root),
        }
        ctx = SimpleNamespace(
            dataset=dataset, view=dataset, selected=[source_id], params=params, trigger=Mock(), set_progress=Mock()
        )
        operator = AugmentWithAlbumentationsX()
        form = json.dumps(operator.resolve_input(ctx).to_json())
        assert "Omitted annotations: ignored" in form
        assert "coco_id, reviewer, tags" in form
        results = []
        for mode in ({PREVIEW_ONLY_FIELD_NAME: True}, {"dry_run": True}, {}):
            ctx.params = {**params, **mode}
            result = operator.execute(ctx)
            assert result["error_count"] == 0, result
            policy = cast(dict[str, Any], result[OUTPUT_METADATA_POLICY])
            assert policy["selected_annotation_fields"] == ["detections"]
            assert policy["excluded_annotation_fields"] == ["ignored"]
            assert policy["excluded_sample_fields"] == ["coco_id", "reviewer", "tags"]
            assert policy["source_tags_copied"] is False
            assert policy["label_ids_preserved"] is False
            exclusions = policy["excluded_label_attributes"]
            assert {item["sample_id"] for item in exclusions} == {source_id}
            assert {(item["field_path"], item["reason"]) for item in exclusions} == {
                ("detections.detections[0].area", "geometry_dependent"),
                ("detections.detections[0].reviewed_at", "not_json_serializable"),
            }
            assert "detections.detections[0].reviewed_at" in str(result["metadata_policy_summary"])
            results.append(result)
            if mode:
                assert len(dataset) == 1
                assert not dataset.list_runs()
                assert not storage_root.exists()
                ctx.trigger.assert_not_called()
        assert (
            results[0][OUTPUT_METADATA_POLICY]
            == results[1][OUTPUT_METADATA_POLICY]
            == results[2][OUTPUT_METADATA_POLICY]
        )
        preview_labels = json.loads(str(results[0][preview_field_name(1, PREVIEW_FIELD_LABELS_JSON)]))
        preview_detection = preview_labels["fields"]["detections"]["detections"][0]
        comparison = json.loads(str(results[0][preview_field_name(1, PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON)]))
        assert {item["field_path"] for item in comparison["dropped_attributes"]} == {
            "detections.detections[0].area",
            "detections.detections[0].reviewed_at",
        }
        output = cast(Any, dataset.exists(SOURCE_SAMPLE_ID_FIELD).first())
        assert output.id != source_id
        assert output[SOURCE_SAMPLE_ID_FIELD] == source_id
        assert output.coco_id is None and output.reviewer is None and output.ignored is None
        assert not {"validation", "user-tag"}.intersection(output.tags)
        assert output.detections.origin == "manual"
        assert output.detections.tags == ["reviewed-container"]
        transformed = output.detections.detections[0]
        assert transformed.id != detection.id
        assert transformed.tags == ["verified"]
        assert transformed.attributes["quality"].value == 0.95
        for name in ("iscrowd", "supercategory", "review", "coco_id"):
            assert transformed[name] == detection[name] == preview_detection["custom_fields"][name]
        assert transformed.bounding_box == pytest.approx(preview_detection["bounding_box"])
        assert transformed.bounding_box[0] == pytest.approx(1 - (95.12 + 45.58) / width)
        assert not transformed.has_field("area") and not transformed.has_field("reviewed_at")
        saved_source = json.loads(dataset[source_id].to_json())
        assert {name: saved_source[name] for name in original_json} == original_json
        assert source_path.read_bytes() == source_bytes
        run_key = str(results[2]["run_key"])
        manifest = FileRunStore(dataset.name, storage_root=storage_root).load_manifest(run_key)
        manifest_json = cast(dict[str, Any], manifest.to_dict())
        assert manifest_json["metadata"]["annotations"][OUTPUT_METADATA_POLICY] == results[2][OUTPUT_METADATA_POLICY]
        json.dumps(manifest_json, allow_nan=False)
        cleanup_run(dataset=cast(Any, dataset), run_key=run_key, storage_root=storage_root, confirmed=True)
        assert len(dataset) == 1 and source_path.read_bytes() == source_bytes
    finally:
        dataset.delete()
