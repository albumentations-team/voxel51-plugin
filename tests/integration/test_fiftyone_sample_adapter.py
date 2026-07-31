from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.core import (
    AugmentationResult,
    HostAdapterError,
    MediaIOError,
    PipelineConfig,
    RunManifest,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.samples import (
    DEFAULT_OUTPUT_TAG,
    RUN_KEY_FIELD,
    SOURCE_SAMPLE_ID_FIELD,
    TRANSFORM_SUMMARY_FIELD,
    FiftyOneSampleAdapter,
    build_run_tag,
)
from albumentationsx_plugin.storage.images import write_rgb_image


def _dataset_name() -> str:
    return f"albumentationsx-adapter-test-{uuid.uuid4().hex}"


def _rgb_array(width: int = 5, height: int = 4) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 1] = 180
    return image


def _write_source_image(root: Path, name: str) -> Path:
    return write_rgb_image(_rgb_array(), root, f"sources/{name}.png")


def _sample(filepath: Path, *, tag: str = "source") -> fo.Sample:
    return fo.Sample(
        filepath=str(filepath),
        tags=[tag],
        metadata=fo.ImageMetadata(width=5, height=4, mime_type="image/png"),
        ground_truth=fo.Classification(label=tag),
    )


def _load_sample(dataset: fo.Dataset, sample_id: str) -> Any:
    return dataset[sample_id]


def _manifest(
    source_sample_ids: tuple[str, ...], output_paths: tuple[str, ...] = ("images/output.png",)
) -> RunManifest:
    return RunManifest(
        run_key="albumentationsx-20260731T140000Z-vox9",
        plugin_version="0.0.0",
        dependency_versions={"fiftyone": "test"},
        pipeline=PipelineConfig(
            transforms=(
                TransformConfig(name="HorizontalFlip", params={"p": 1.0}),
                TransformConfig(name="RandomBrightnessContrast", params={"contrast_range": [0.1, 0.2]}),
            )
        ),
        source_sample_ids=source_sample_ids,
        output_paths=output_paths,
    )


@pytest.mark.integration
def test_sample_adapter_iterates_selected_samples_in_requested_order(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        first_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "first"), tag="first"))
        second_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "second"), tag="second"))

        adapter = FiftyOneSampleAdapter(
            dataset=dataset,
            selected_sample_ids=(second_id, first_id),
            selected_label_fields=("ground_truth",),
        )

        inputs = list(adapter.iter_inputs())

        assert [item.sample_id for item in inputs] == [second_id, first_id]
        assert all(item.media_type == "image" for item in inputs)
        assert all(item.width == 5 and item.height == 4 for item in inputs)
        assert all(item.selected_label_fields == ("ground_truth",) for item in inputs)
        assert inputs[0].metadata["dataset_name"] == dataset_name
        assert inputs[0].metadata["tags"] == ["second"]
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_sample_adapter_iterates_current_view_when_no_samples_are_selected(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        kept_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "kept"), tag="keep"))
        dataset.add_sample(_sample(_write_source_image(tmp_path, "skipped"), tag="skip"))
        view = dataset.match_tags("keep")

        inputs = list(FiftyOneSampleAdapter(dataset=dataset, view=view).iter_inputs())

        assert [item.sample_id for item in inputs] == [kept_id]
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_sample_adapter_creates_output_sample_without_mutating_source(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, "source")
        source_id = dataset.add_sample(_sample(source_path, tag="source"))
        source_before = _load_sample(dataset, source_id)
        source_tags_before = tuple(source_before.tags)
        source_filepath_before = source_before.filepath
        output_path = write_rgb_image(_rgb_array(), tmp_path, "outputs/augmented.png")
        manifest = _manifest(source_sample_ids=(source_id,), output_paths=("outputs/augmented.png",))
        result = AugmentationResult(
            source_sample_id=source_id,
            output_filepath=str(output_path),
            replay={"applied": True},
        )

        created_id = FiftyOneSampleAdapter(dataset).create_output_sample(result, manifest)

        assert len(dataset) == 2
        source_after = _load_sample(dataset, source_id)
        assert tuple(source_after.tags) == source_tags_before
        assert source_after.filepath == source_filepath_before

        created = _load_sample(dataset, created_id)
        assert created.filepath == str(output_path.resolve())
        assert DEFAULT_OUTPUT_TAG in created.tags
        assert build_run_tag(manifest.run_key) in created.tags
        assert created.get_field(SOURCE_SAMPLE_ID_FIELD) == source_id
        assert created.get_field(RUN_KEY_FIELD) == manifest.run_key
        assert created.get_field(TRANSFORM_SUMMARY_FIELD) == (
            "HorizontalFlip(p=1.0) -> RandomBrightnessContrast(contrast_range=[0.1,0.2])"
        )
        assert created.metadata.width == 5
        assert created.metadata.height == 4
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_sample_adapter_reports_missing_source_files(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        sample_id = dataset.add_sample(fo.Sample(filepath=str(tmp_path / "missing.png")))

        with pytest.raises(MediaIOError) as error:
            list(FiftyOneSampleAdapter(dataset, selected_sample_ids=(sample_id,)).iter_inputs())

        assert error.value.context["reason"] == "missing_file"
        assert error.value.context["sample_id"] == sample_id
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_sample_adapter_reports_unsupported_media_type() -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name, media_type="video")

        with pytest.raises(HostAdapterError) as error:
            list(FiftyOneSampleAdapter(dataset).iter_inputs())

        assert error.value.context["reason"] == "unsupported_media_type"
        assert error.value.context["media_type"] == "video"
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_sample_adapter_reports_output_errors(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "source")))
        manifest = _manifest(source_sample_ids=(source_id,))

        with pytest.raises(HostAdapterError) as missing_output_error:
            FiftyOneSampleAdapter(dataset).create_output_sample(
                AugmentationResult(source_sample_id=source_id),
                manifest,
            )

        with pytest.raises(HostAdapterError) as mismatch_error:
            FiftyOneSampleAdapter(dataset).create_output_sample(
                AugmentationResult(source_sample_id="other", output_filepath=str(tmp_path / "missing-output.png")),
                manifest,
            )

        with pytest.raises(MediaIOError) as missing_file_error:
            FiftyOneSampleAdapter(dataset).create_output_sample(
                AugmentationResult(source_sample_id=source_id, output_filepath=str(tmp_path / "missing-output.png")),
                manifest,
            )

        assert missing_output_error.value.context["reason"] == "missing_output_filepath"
        assert mismatch_error.value.context["reason"] == "source_sample_not_in_manifest"
        assert missing_file_error.value.context["reason"] == "missing_output_file"
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
