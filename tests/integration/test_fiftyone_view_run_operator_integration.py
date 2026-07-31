from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import STORAGE_ROOT_PARAM_NAME, ViewAlbumentationsXRun
from albumentationsx_plugin.hosts.fiftyone.run_summary import RUN_STATUS_MISSING, RUN_STATUS_OK
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image


def _dataset_name() -> str:
    return f"albumentationsx-view-run-test-{uuid.uuid4().hex}"


def _rgb_array(width: int = 5, height: int = 4) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None]
    image[..., 2] = 120
    return image


def _write_source_image(root: Path, name: str) -> Path:
    return write_rgb_image(_rgb_array(), root, f"sources/{name}.png")


def _sample(filepath: Path) -> fo.Sample:
    return fo.Sample(
        filepath=str(filepath),
        tags=["source"],
        metadata=fo.ImageMetadata(width=5, height=4, mime_type="image/png"),
    )


@pytest.mark.integration
def test_view_run_operator_reads_manifest_summary_without_mutating_dataset(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        sample_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "source")))
        storage_root = tmp_path / "plugin-storage"
        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=storage_root,
        )
        before_count = len(dataset)

        context = SimpleNamespace(
            dataset=dataset,
            params={"run_key": result.run_key, STORAGE_ROOT_PARAM_NAME: str(storage_root)},
        )

        summary = ViewAlbumentationsXRun().execute(context)

        assert len(dataset) == before_count
        assert summary["status"] == RUN_STATUS_OK
        assert summary["run_key"] == result.run_key
        assert summary["source_count"] == 1
        assert summary["created_count"] == 1
        assert summary["output_count"] == 1
        assert summary["available_output_count"] == 1
        assert summary["missing_output_count"] == 0
        assert summary["error_count"] == 0
        assert summary["replay_available"] is True
        assert summary["output_tag"] == result.output_tag
        assert summary["manifest_path"] == result.manifest_path
        assert summary["fiftyone_run_key"] == result.fiftyone_run_key
        assert "HorizontalFlip" in str(summary["pipeline_config_json"])

        FileRunStore(dataset.name, storage_root=storage_root).delete_manifest(result.run_key)
        missing_summary = ViewAlbumentationsXRun().execute(context)

        assert len(dataset) == before_count
        assert missing_summary["status"] == RUN_STATUS_MISSING
        assert "manifest" in str(missing_summary["message"]).lower()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
