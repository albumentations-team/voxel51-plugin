from __future__ import annotations

import json
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
    STORAGE_ROOT_PARAM_NAME,
    DeleteAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    STORAGE_ROOT_PARAM_NAME as VIEW_STORAGE_ROOT_PARAM_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import CLEANUP_STATUS_CLEANED, CLEANUP_STATUS_OK
from albumentationsx_plugin.hosts.fiftyone.run_summary import RUN_STATUS_CLEANED
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image


def _dataset_name() -> str:
    return f"albumentationsx-delete-run-test-{uuid.uuid4().hex}"


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


def _load_sample(dataset: fo.Dataset, sample_id: str) -> Any:
    return cast(Any, dataset[sample_id])


@pytest.mark.integration
def test_delete_run_operator_removes_outputs_without_touching_source_and_is_idempotent(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, "source")
        source_id = dataset.add_sample(_sample(source_path))
        storage_root = tmp_path / "plugin-storage"
        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(source_id,),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=storage_root,
        )
        store = FileRunStore(dataset.name, storage_root=storage_root)
        manifest = store.load_manifest(result.run_key)
        created_id = manifest.created_sample_ids[0]
        output_path = Path(result.output_dir) / manifest.output_paths[0]
        assert output_path.exists()
        assert len(dataset) == 2
        assert dataset.has_run(result.fiftyone_run_key)

        context = SimpleNamespace(
            dataset=dataset,
            params={
                "run_key": result.run_key,
                CONFIRM_FIELD_NAME: True,
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
            },
        )

        cleanup_result = DeleteAlbumentationsXRun().execute(context)

        assert cleanup_result["status"] == CLEANUP_STATUS_OK
        assert cleanup_result["deleted_sample_count"] == 1
        assert cleanup_result["deleted_file_count"] == 1
        assert cleanup_result["custom_run_deleted"] is True
        assert len(dataset) == 1
        assert str(_load_sample(dataset, source_id).filepath) == str(source_path)
        assert source_path.exists()
        assert dataset.select([created_id]).values("id") == []
        assert not output_path.exists()
        assert store.manifest_path(result.run_key).exists()
        assert not dataset.has_run(result.fiftyone_run_key)

        delete_input = (
            DeleteAlbumentationsXRun()
            .resolve_input(SimpleNamespace(dataset=dataset, params={STORAGE_ROOT_PARAM_NAME: str(storage_root)}))
            .to_json()
        )
        delete_run_key_property = delete_input["type"]["properties"]["run_key"]
        assert delete_run_key_property["type"]["name"] == "String"
        assert "No deletable AlbumentationsX runs" in delete_run_key_property["view"]["description"]

        view_input = (
            ViewAlbumentationsXRun()
            .resolve_input(SimpleNamespace(dataset=dataset, params={VIEW_STORAGE_ROOT_PARAM_NAME: str(storage_root)}))
            .to_json()
        )
        assert result.run_key in view_input["type"]["properties"]["run_key"]["type"]["values"]
        view_summary = ViewAlbumentationsXRun().execute(
            SimpleNamespace(
                dataset=dataset,
                params={"run_key": result.run_key, VIEW_STORAGE_ROOT_PARAM_NAME: str(storage_root)},
            )
        )
        assert view_summary["status"] == RUN_STATUS_CLEANED
        assert view_summary["cleanup_status"] == "cleaned"
        assert isinstance(view_summary["cleaned_at"], str)
        cleaned_outputs = json.loads(str(view_summary["generated_outputs_json"]))
        cleaned_replay = json.loads(str(view_summary["selected_replay_json"]))
        assert cleaned_outputs[0]["status"] == "cleaned"
        assert cleaned_outputs[0]["generated_sample_available"] is False
        assert cleaned_outputs[0]["output_file_available"] is False
        assert cleaned_replay["source_sample_id"] == source_id
        assert isinstance(cleaned_replay["replay"], dict)

        repeated_result = DeleteAlbumentationsXRun().execute(context)

        assert repeated_result["status"] == CLEANUP_STATUS_CLEANED
        assert repeated_result["deleted_sample_count"] == 0
        assert repeated_result["skipped_sample_count"] == 1
        assert repeated_result["deleted_file_count"] == 0
        assert repeated_result["skipped_file_count"] == 1
        assert repeated_result["custom_run_deleted"] is False
        assert repeated_result["custom_run_missing"] is True
        assert len(dataset) == 1
        assert source_path.exists()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
