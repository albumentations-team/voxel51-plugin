from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation
from albumentationsx_plugin.hosts.fiftyone.operators.delete_run import (
    CONFIRM_FIELD_NAME,
    DeleteAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.operators.delete_run import (
    STORAGE_ROOT_PARAM_NAME as DELETE_STORAGE_ROOT_PARAM,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    STORAGE_ROOT_PARAM_NAME as VIEW_STORAGE_ROOT_PARAM,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import CLEANUP_STATUS_OK
from albumentationsx_plugin.hosts.fiftyone.run_summary import RUN_STATUS_OK
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG
from scripts.create_demo_dataset import DEMO_SAMPLES, create_demo_dataset, delete_demo_dataset


@pytest.mark.integration
@pytest.mark.smoke
def test_mvp_demo_workflow_creates_inspects_and_deletes_a_run(tmp_path) -> None:
    dataset_name = f"albumentationsx-mvp-smoke-{uuid.uuid4().hex}"
    data_root = tmp_path / "demo-data"
    storage_root = tmp_path / "plugin-storage"

    try:
        create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        dataset = fo.load_dataset(dataset_name)
        source_samples = list(dataset)
        source_ids = tuple(str(sample.id) for sample in source_samples)
        source_filepaths = {str(sample.id): str(sample.filepath) for sample in source_samples}
        selected_sample_id = source_ids[0]

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(selected_sample_id,),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=storage_root,
        )

        output_samples = list(dataset.match_tags(DEFAULT_OUTPUT_TAG))
        assert len(dataset) == len(DEMO_SAMPLES) + 1
        assert len(output_samples) == 1
        assert Path(output_samples[0].filepath).exists()
        output = output_samples[0]
        assert output.ground_truth.label == source_samples[0].ground_truth.label
        assert len(output.detections.detections) == 1
        assert len(output.keypoints.keypoints) == 1
        assert len(output.polylines.polylines) == 1
        assert np.asarray(output.heatmap.map).shape == np.asarray(source_samples[0].heatmap.map).shape
        assert np.asarray(output.segmentation.mask).shape == np.asarray(source_samples[0].segmentation.mask).shape
        assert dataset.has_run(result.fiftyone_run_key)

        summary_context = SimpleNamespace(
            dataset=dataset,
            params={"run_key": result.run_key, VIEW_STORAGE_ROOT_PARAM: str(storage_root)},
        )
        summary = ViewAlbumentationsXRun().execute(summary_context)

        assert summary["status"] == RUN_STATUS_OK
        assert summary["created_count"] == 1
        assert summary["available_output_count"] == 1
        assert summary["replay_available"] is True

        delete_context = SimpleNamespace(
            dataset=dataset,
            params={
                "run_key": result.run_key,
                CONFIRM_FIELD_NAME: True,
                DELETE_STORAGE_ROOT_PARAM: str(storage_root),
            },
        )
        cleanup = DeleteAlbumentationsXRun().execute(delete_context)

        assert cleanup["status"] == CLEANUP_STATUS_OK
        assert cleanup["deleted_sample_count"] == 1
        assert cleanup["deleted_file_count"] == 1
        assert len(dataset) == len(DEMO_SAMPLES)
        assert not dataset.has_run(result.fiftyone_run_key)
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 0
        for sample_id, filepath in source_filepaths.items():
            sample = _load_sample(dataset, sample_id)
            assert str(sample.filepath) == filepath
            assert Path(filepath).exists()
    finally:
        delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)


def _load_sample(dataset: fo.Dataset, sample_id: str) -> Any:
    return cast(Any, dataset[sample_id])
