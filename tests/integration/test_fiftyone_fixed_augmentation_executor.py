from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.core import InvalidParameterError
from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation
from albumentationsx_plugin.hosts.fiftyone.samples import (
    DEFAULT_OUTPUT_TAG,
    RUN_KEY_FIELD,
    SOURCE_SAMPLE_ID_FIELD,
    build_run_tag,
)
from albumentationsx_plugin.storage.images import load_rgb_image, write_rgb_image


def _dataset_name() -> str:
    return f"albumentationsx-fixed-executor-test-{uuid.uuid4().hex}"


def _rgb_array(width: int = 5, height: int = 4) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None]
    image[..., 2] = 120
    return image


def _write_source_image(root: Path, name: str, *, width: int = 5, height: int = 4) -> Path:
    return write_rgb_image(_rgb_array(width=width, height=height), root, f"sources/{name}.png")


def _sample(filepath: Path, *, width: int = 5, height: int = 4, tag: str = "source") -> fo.Sample:
    return fo.Sample(
        filepath=str(filepath),
        tags=[tag],
        metadata=fo.ImageMetadata(width=width, height=height, mime_type="image/png"),
    )


def _output_samples(dataset: fo.Dataset) -> list[Any]:
    return list(dataset.match_tags(DEFAULT_OUTPUT_TAG))


def _load_sample(dataset: fo.Dataset, sample_id: str) -> Any:
    return cast(Any, dataset[sample_id])


@pytest.mark.integration
def test_fixed_augmentation_executor_creates_outputs_for_selected_samples(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        first_path = _write_source_image(tmp_path, "first")
        second_path = _write_source_image(tmp_path, "second", width=6, height=5)
        first_id = dataset.add_sample(_sample(first_path, tag="first"))
        second_id = dataset.add_sample(_sample(second_path, width=6, height=5, tag="second"))
        source_filepaths = {
            first_id: _load_sample(dataset, first_id).filepath,
            second_id: _load_sample(dataset, second_id).filepath,
        }

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(first_id, second_id),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 2
        assert result.created_count == 2
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert result.output_dir.startswith(str(tmp_path / "plugin-storage"))
        assert len(dataset) == 4
        assert _load_sample(dataset, first_id).filepath == source_filepaths[first_id]
        assert _load_sample(dataset, second_id).filepath == source_filepaths[second_id]

        created = _output_samples(dataset)
        assert len(created) == 2
        for sample in created:
            source_id = sample.get_field(SOURCE_SAMPLE_ID_FIELD)
            assert source_id in {first_id, second_id}
            assert sample.get_field(RUN_KEY_FIELD) == result.run_key
            assert build_run_tag(result.run_key) in sample.tags
            assert Path(sample.filepath).is_file()
            source_image = load_rgb_image(source_filepaths[source_id]).data
            output_image = load_rgb_image(sample.filepath).data
            np.testing.assert_array_equal(output_image, source_image[:, ::-1, :])
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_dry_run_does_not_write_outputs(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        sample_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "source")))

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "transform": "HorizontalFlip",
                "dry_run": True,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 1
        assert result.created_count == 0
        assert result.error_count == 0
        assert len(dataset) == 1
        assert not Path(result.output_dir).exists()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_rejects_invalid_params_before_writing(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        sample_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "source")))

        with pytest.raises(InvalidParameterError) as error:
            execute_fixed_augmentation(
                dataset=dataset,
                selected_sample_ids=(sample_id,),
                params={
                    "transform": "HorizontalFlip",
                    "outputs_per_sample": 4,
                },
                storage_root=tmp_path / "plugin-storage",
            )

        assert error.value.context["parameter_name"] == "outputs_per_sample"
        assert len(dataset) == 1
        assert not (tmp_path / "plugin-storage").exists()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_reports_partial_per_sample_failures(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        large_id = dataset.add_sample(
            _sample(_write_source_image(tmp_path, "large", width=8, height=8), width=8, height=8)
        )
        small_id = dataset.add_sample(
            _sample(_write_source_image(tmp_path, "small", width=4, height=4), width=4, height=4)
        )

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(large_id, small_id),
            params={
                "transform": "RandomCrop",
                "crop_width": 8,
                "crop_height": 8,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 2
        assert result.created_count == 1
        assert result.skipped_count == 1
        assert result.error_count == 1
        assert len(dataset) == 3
        assert result.errors[0]["code"] == "invalid_parameter"
        error_context = result.errors[0]["context"]
        assert isinstance(error_context, dict)
        assert error_context["sample_id"] == small_id
        assert error_context["parameter_name"] == "height"
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
