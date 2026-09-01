from __future__ import annotations

import uuid
from pathlib import Path

import fiftyone as fo
import numpy as np
import pytest

from scripts.create_demo_dataset import (
    ANNOTATION_DEMO_SAMPLES,
    DEMO_SAMPLES,
    MASK_DEMO_SAMPLES,
    VALIDATION_DEMO_SAMPLES,
    create_demo_dataset,
    create_demo_dataset_suite,
    delete_demo_dataset,
    delete_demo_dataset_suite,
    describe_demo_dataset,
    describe_demo_dataset_suite,
)


@pytest.mark.integration
def test_create_list_and_delete_demo_dataset(tmp_path) -> None:
    dataset_name = f"albumentationsx-demo-test-{uuid.uuid4().hex}"
    data_root = tmp_path / "demo-data"

    try:
        created = create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        listed = describe_demo_dataset(dataset_name=dataset_name, data_root=data_root)

        assert created.exists is True
        assert created.sample_count == len(DEMO_SAMPLES)
        assert created.image_count == len(DEMO_SAMPLES)
        assert listed == created

        dataset = fo.load_dataset(dataset_name)
        samples_by_demo_id: dict[str, fo.Sample] = {}
        for sample in dataset:
            demo_id = sample.get_field("demo_id")
            assert isinstance(demo_id, str)
            samples_by_demo_id[demo_id] = sample

        assert dataset.persistent is True
        assert sorted(samples_by_demo_id) == [spec.demo_id for spec in DEMO_SAMPLES]
        for spec in DEMO_SAMPLES:
            sample = samples_by_demo_id[spec.demo_id]
            assert "albumentationsx-demo" in sample.tags
            assert sample.metadata.width == spec.width
            assert sample.metadata.height == spec.height
            assert sample.ground_truth.label == spec.label
            assert len(sample.detections.detections) == 1
            assert len(sample.keypoints.keypoints) == 1
            assert len(sample.polylines.polylines) == 1
            assert np.asarray(sample.heatmap.map).shape == (spec.height, spec.width)
            assert np.asarray(sample.segmentation.mask).shape == (spec.height, spec.width)

        deleted = delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)

        assert deleted.exists is True
        assert dataset_name not in fo.list_datasets()
        assert not data_root.exists()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_create_list_and_delete_demo_dataset_suite(tmp_path) -> None:
    dataset_name_prefix = f"albumentationsx-suite-test-{uuid.uuid4().hex}-"
    data_root = tmp_path / "demo-suite-data"
    suite_keys = ("annotations", "masks", "validation")
    expected_counts = {
        f"{dataset_name_prefix}albumentationsx-demo-annotations": len(ANNOTATION_DEMO_SAMPLES),
        f"{dataset_name_prefix}albumentationsx-demo-masks": len(MASK_DEMO_SAMPLES),
        f"{dataset_name_prefix}albumentationsx-demo-validation": len(VALIDATION_DEMO_SAMPLES),
    }

    try:
        created = create_demo_dataset_suite(
            suite_keys=suite_keys,
            data_root=data_root,
            dataset_name_prefix=dataset_name_prefix,
        )
        listed = describe_demo_dataset_suite(
            suite_keys=suite_keys,
            data_root=data_root,
            dataset_name_prefix=dataset_name_prefix,
        )

        assert listed == created
        assert {summary.dataset_name for summary in created} == set(expected_counts)
        for summary in created:
            assert summary.exists is True
            assert summary.sample_count == expected_counts[summary.dataset_name]

        annotation_dataset = fo.load_dataset(f"{dataset_name_prefix}albumentationsx-demo-annotations")
        multiple_sample = annotation_dataset.match_tags("multiple-spatial-labels").first()
        assert multiple_sample is not None
        assert len(multiple_sample.detections.detections) == 2
        assert len(multiple_sample.keypoints.keypoints) == 2
        assert len(multiple_sample.polylines.polylines) == 2

        boundary_sample = annotation_dataset.match_tags("boundary-geometry").first()
        assert boundary_sample is not None
        assert boundary_sample.detections.detections[0].bounding_box[0] == 0.0
        assert boundary_sample.keypoints.keypoints[0].points[0] == [0.02, 0.02]

        empty_sample = annotation_dataset.match_tags("empty-label-containers").first()
        assert empty_sample is not None
        assert len(empty_sample.detections.detections) == 0
        assert len(empty_sample.keypoints.keypoints) == 0
        assert len(empty_sample.polylines.polylines) == 0

        mask_dataset = fo.load_dataset(f"{dataset_name_prefix}albumentationsx-demo-masks")
        mask_sample = mask_dataset.match_tags("file-backed-segmentation").first()
        assert mask_sample is not None
        assert mask_sample.segmentation.mask_path is not None
        assert (data_root / f"{dataset_name_prefix}albumentationsx-demo-masks" / "masks").exists()

        file_backed_label_sample = mask_dataset.match_tags("file-backed-detection-and-heatmap").first()
        assert file_backed_label_sample is not None
        assert file_backed_label_sample.detections.detections[0].mask_path is not None
        assert file_backed_label_sample.heatmap.map_path is not None

        validation_dataset = fo.load_dataset(f"{dataset_name_prefix}albumentationsx-demo-validation")
        validation_cases = {
            sample.get_field("validation_case")
            for sample in validation_dataset
            if isinstance(sample.get_field("validation_case"), str)
        }
        assert {
            "heatmap_with_image_only_transform",
            "missing_source_image",
            "missing_segmentation_mask_file",
            "invalid_segmentation_mask_shape",
            "missing_heatmap_map_file",
            "unsupported_label_field",
            "crop_larger_than_image",
        } <= validation_cases

        missing_image = validation_dataset.match_tags("missing-source-image").first()
        assert missing_image is not None
        assert not Path(missing_image.filepath).exists()

        deleted = delete_demo_dataset_suite(
            suite_keys=suite_keys,
            data_root=data_root,
            delete_files=True,
            dataset_name_prefix=dataset_name_prefix,
        )

        assert all(summary.exists for summary in deleted)
        assert all(dataset_name not in fo.list_datasets() for dataset_name in expected_counts)
        assert not any((data_root / dataset_name).exists() for dataset_name in expected_counts)
    finally:
        for dataset_name in expected_counts:
            if dataset_name in fo.list_datasets():
                fo.delete_dataset(dataset_name)
