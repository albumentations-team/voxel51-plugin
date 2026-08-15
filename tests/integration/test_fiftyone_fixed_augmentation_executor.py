from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.core import InvalidParameterError, MediaIOError, RunManifest
from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.operators.delete_run import (
    STORAGE_ROOT_PARAM_NAME as DELETE_STORAGE_ROOT_PARAM_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.operators.delete_run import (
    DeleteAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    STORAGE_ROOT_PARAM_NAME as VIEW_STORAGE_ROOT_PARAM_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.samples import (
    DEFAULT_OUTPUT_TAG,
    RUN_KEY_FIELD,
    SOURCE_SAMPLE_ID_FIELD,
    build_run_tag,
)
from albumentationsx_plugin.storage import FileRunStore
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


def _annotated_sample(filepath: Path) -> fo.Sample:
    mask = np.zeros((8, 10), dtype=np.uint8)
    mask[:, :3] = 1
    return fo.Sample(
        filepath=str(filepath),
        tags=["source"],
        metadata=fo.ImageMetadata(width=10, height=8, mime_type="image/png"),
        ground_truth=fo.Classification(label="cat", confidence=0.95),
        detections=fo.Detections(
            detections=[
                fo.Detection(
                    label="object",
                    bounding_box=[0.1, 0.25, 0.2, 0.5],
                    confidence=0.8,
                    attributes={"source": fo.CategoricalAttribute(value="manual")},
                )
            ]
        ),
        keypoints=fo.Keypoints(
            keypoints=[
                fo.Keypoint(
                    label="nose",
                    points=[[0.2, 0.375]],
                    confidence=[0.9],
                    attributes={"side": fo.CategoricalAttribute(value="left")},
                )
            ]
        ),
        segmentation=fo.Segmentation(mask=mask),
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
        assert result.manifest_path == str(Path(result.output_dir) / "manifest.json")
        assert result.fiftyone_run_key in dataset.list_runs()
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

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert manifest.run_key == result.run_key
        assert result.source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES
        assert manifest.metadata[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_SELECTED_SAMPLES
        assert manifest.metadata["source_count"] == 2
        assert set(manifest.created_sample_ids) == {str(sample.id) for sample in created}
        assert set(manifest.output_paths) == {
            Path(sample.filepath).relative_to(Path(result.output_dir)).as_posix() for sample in created
        }
        assert manifest.counters == {"processed": 2, "created": 2, "skipped": 0, "errors": 0, "outputs": 2}
        assert manifest.metadata["output_tag"] == DEFAULT_OUTPUT_TAG
        assert set(manifest.dependency_versions) == {"albumentationsx", "albu-spec", "fiftyone"}
        assert len(manifest.replay_records) == 2
        first_replay = manifest.replay_records[0]
        assert first_replay["source_sample_id"] in {first_id, second_id}
        assert first_replay["output_path"] in manifest.output_paths
        assert isinstance(first_replay["replay"], dict)

        run_results = dataset.load_run_results(result.fiftyone_run_key, load_view=False)
        assert run_results is not None
        assert run_results.plugin_run_key == result.run_key
        assert run_results.manifest["run_key"] == result.run_key
        assert run_results.manifest_path == result.manifest_path
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_processes_current_view_scope(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        kept_path = _write_source_image(tmp_path, "kept")
        skipped_path = _write_source_image(tmp_path, "skipped", width=6, height=5)
        kept_id = dataset.add_sample(_sample(kept_path, tag="keep"))
        skipped_id = dataset.add_sample(_sample(skipped_path, width=6, height=5, tag="skip"))
        view = dataset.match_tags("keep")

        result = execute_fixed_augmentation(
            dataset=dataset,
            view=view,
            selected_sample_ids=(),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_CURRENT_VIEW,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.source_scope == EXECUTION_SCOPE_CURRENT_VIEW
        assert result.processed_count == 1
        assert result.created_count == 1
        created = _output_samples(dataset)
        assert len(created) == 1
        assert created[0].get_field(SOURCE_SAMPLE_ID_FIELD) == kept_id
        assert created[0].get_field(SOURCE_SAMPLE_ID_FIELD) != skipped_id

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert manifest.source_sample_ids == (kept_id,)
        assert manifest.metadata[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_CURRENT_VIEW
        assert manifest.metadata["source_count"] == 1
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_entire_dataset_scope_ignores_view(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        first_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "first"), tag="keep"))
        second_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "second"), tag="skip"))
        view = dataset.match_tags("keep")

        result = execute_fixed_augmentation(
            dataset=dataset,
            view=view,
            selected_sample_ids=(),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_ENTIRE_DATASET,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.source_scope == EXECUTION_SCOPE_ENTIRE_DATASET
        assert result.processed_count == 2
        assert result.created_count == 2
        created_source_ids = {sample.get_field(SOURCE_SAMPLE_ID_FIELD) for sample in _output_samples(dataset)}
        assert created_source_ids == {first_id, second_id}

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert set(manifest.source_sample_ids) == {first_id, second_id}
        assert manifest.metadata[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_ENTIRE_DATASET
        assert manifest.metadata["source_count"] == 2
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_uses_optional_run_label_for_run_keys_and_selectors(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, "source")
        sample_id = dataset.add_sample(_sample(source_path))
        storage_root = tmp_path / "plugin-storage"

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
                "run_label": "Cats crop test",
            },
            storage_root=storage_root,
        )

        assert result.run_key.startswith("cats-crop-test-albumentationsx-")
        assert Path(result.output_dir).name == result.run_key
        assert result.fiftyone_run_key.startswith("cats_crop_test_albumentationsx_")
        created = _output_samples(dataset)
        assert len(created) == 1
        assert created[0].get_field(RUN_KEY_FIELD) == result.run_key
        assert build_run_tag(result.run_key) in created[0].tags

        manifest = FileRunStore(dataset.name, storage_root=storage_root).load_manifest(result.run_key)
        assert manifest.metadata["run_label"] == "Cats crop test"
        assert manifest.metadata["run_label_slug"] == "cats-crop-test"

        view_context = SimpleNamespace(
            dataset=dataset,
            params={VIEW_STORAGE_ROOT_PARAM_NAME: str(storage_root)},
        )
        delete_context = SimpleNamespace(
            dataset=dataset,
            params={DELETE_STORAGE_ROOT_PARAM_NAME: str(storage_root)},
        )
        view_input = ViewAlbumentationsXRun().resolve_input(view_context).to_json()
        delete_input = DeleteAlbumentationsXRun().resolve_input(delete_context).to_json()

        assert result.run_key in view_input["type"]["properties"]["run_key"]["type"]["values"]
        assert result.run_key in delete_input["type"]["properties"]["run_key"]["type"]["values"]

        summary = ViewAlbumentationsXRun().execute(
            SimpleNamespace(
                dataset=dataset,
                params={"run_key": result.run_key, VIEW_STORAGE_ROOT_PARAM_NAME: str(storage_root)},
            )
        )
        assert summary["run_label"] == "Cats crop test"
        assert summary["run_label_slug"] == "cats-crop-test"
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_persists_ordered_transform_chain(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, "source")
        sample_id = dataset.add_sample(_sample(source_path))

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "pipeline_step_count": 2,
                "transform": "HorizontalFlip",
                "p": 1.0,
                "step_2_transform": "HorizontalFlip",
                "step_2_p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 1
        assert result.created_count == 1
        created = _output_samples(dataset)
        assert len(created) == 1
        source_image = load_rgb_image(source_path).data
        output_image = load_rgb_image(created[0].filepath).data
        np.testing.assert_array_equal(output_image, source_image)

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert [transform.name for transform in manifest.pipeline.transforms] == ["HorizontalFlip", "HorizontalFlip"]
        assert len(manifest.replay_records) == 1
        replay = manifest.replay_records[0]["replay"]
        assert isinstance(replay, dict)
        transforms = replay["transforms"]
        assert isinstance(transforms, list)
        assert [transform["__class_fullname__"] for transform in transforms] == ["HorizontalFlip", "HorizontalFlip"]
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_transforms_supported_annotations(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, "annotated", width=10, height=8)
        sample_id = dataset.add_sample(_annotated_sample(source_path))
        source = _load_sample(dataset, sample_id)
        source_mask = np.asarray(source.segmentation.mask)

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 1
        assert result.created_count == 1
        assert result.error_count == 0
        created = _output_samples(dataset)
        assert len(created) == 1
        output = created[0]

        assert output.ground_truth.label == "cat"
        assert output.ground_truth.confidence == pytest.approx(0.95)

        assert len(output.detections.detections) == 1
        detection = output.detections.detections[0]
        assert detection.label == "object"
        assert detection.confidence == pytest.approx(0.8)
        assert detection.attributes["source"].value == "manual"
        assert detection.bounding_box == pytest.approx([0.7, 0.25, 0.2, 0.5])

        assert len(output.keypoints.keypoints) == 1
        keypoint = output.keypoints.keypoints[0]
        assert keypoint.label == "nose"
        assert keypoint.attributes["side"].value == "left"
        assert keypoint.points[0] == pytest.approx([0.7, 0.375])
        assert keypoint.confidence == pytest.approx([0.9])

        np.testing.assert_array_equal(np.asarray(output.segmentation.mask), source_mask[:, ::-1])

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        annotations = manifest.metadata["annotations"]
        assert isinstance(annotations, dict)
        assert annotations["fields"] == ["detections", "ground_truth", "keypoints", "segmentation"]
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("transform_name", "params", "expected_group"),
    (
        ("VerticalFlip", {"p": 1.0}, "geometry"),
        ("ToGray", {"method": "average", "p": 1.0}, "color"),
        ("Blur", {"blur_range": [3, 3], "p": 1.0}, "blur"),
        ("CoarseDropout", {"p": 1.0}, "dropout"),
    ),
)
def test_fixed_augmentation_executor_runs_catalog_backed_transform_groups(
    tmp_path,
    transform_name: str,
    params: dict[str, object],
    expected_group: str,
) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        source_path = _write_source_image(tmp_path, f"source-{expected_group}", width=8, height=6)
        sample_id = dataset.add_sample(_sample(source_path, width=8, height=6))

        result = execute_fixed_augmentation(
            dataset=dataset,
            selected_sample_ids=(sample_id,),
            params={
                "transform": transform_name,
                "outputs_per_sample": 1,
                "dry_run": False,
                **params,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.processed_count == 1
        assert result.created_count == 1
        assert result.error_count == 0
        created = _output_samples(dataset)
        assert len(created) == 1

        source_image = load_rgb_image(source_path).data
        output_image = load_rgb_image(created[0].filepath).data
        assert output_image.shape == source_image.shape
        assert output_image.dtype == source_image.dtype
        if expected_group == "geometry":
            np.testing.assert_array_equal(output_image, source_image[::-1, :, :])
        if expected_group == "color":
            np.testing.assert_array_equal(output_image[..., 0], output_image[..., 1])
            np.testing.assert_array_equal(output_image[..., 1], output_image[..., 2])

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert [transform.name for transform in manifest.pipeline.transforms] == [transform_name]
        replay = manifest.replay_records[0]["replay"]
        assert isinstance(replay, dict)
        replay_transforms = replay["transforms"]
        assert isinstance(replay_transforms, list)
        replay_transform = replay_transforms[0]
        assert isinstance(replay_transform, dict)
        assert replay_transform["__class_fullname__"] == transform_name
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_dry_run_does_not_write_outputs(tmp_path) -> None:
    dataset_name = _dataset_name()
    try:
        dataset = fo.Dataset(dataset_name)
        dataset.add_sample(_sample(_write_source_image(tmp_path, "source"), tag="keep"))
        dataset.add_sample(_sample(_write_source_image(tmp_path, "other"), tag="skip"))
        view = dataset.match_tags("keep")

        result = execute_fixed_augmentation(
            dataset=dataset,
            view=view,
            selected_sample_ids=(),
            params={
                "transform": "HorizontalFlip",
                "dry_run": True,
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_CURRENT_VIEW,
            },
            storage_root=tmp_path / "plugin-storage",
        )

        assert result.source_scope == EXECUTION_SCOPE_CURRENT_VIEW
        assert result.processed_count == 1
        assert result.created_count == 0
        assert result.error_count == 0
        assert len(dataset) == 2
        assert not Path(result.output_dir).exists()
        assert result.manifest_path == ""
        assert not dataset.has_run(result.fiftyone_run_key)
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

        manifest = FileRunStore(dataset.name, storage_root=tmp_path / "plugin-storage").load_manifest(result.run_key)
        assert manifest.source_sample_ids == (large_id, small_id)
        assert len(manifest.created_sample_ids) == 1
        assert len(manifest.output_paths) == 1
        assert manifest.counters == {"processed": 2, "created": 1, "skipped": 1, "errors": 1, "outputs": 1}
        manifest_error = manifest.errors[0]
        manifest_error_context = manifest_error["context"]
        assert isinstance(manifest_error_context, dict)
        assert manifest_error_context["sample_id"] == small_id
        assert manifest_error_context["output_index"] == 0
        assert result.fiftyone_run_key in dataset.list_runs()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)


@pytest.mark.integration
def test_fixed_augmentation_executor_rolls_back_sample_when_manifest_checkpoint_fails(tmp_path, monkeypatch) -> None:
    dataset_name = _dataset_name()
    original_save_manifest = FileRunStore.save_manifest
    save_calls = 0

    def failing_save_manifest(self: FileRunStore, manifest: RunManifest) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 3:
            raise MediaIOError(
                filepath=str(self.manifest_path(manifest.run_key)),
                message="Simulated manifest checkpoint failure.",
                context={"reason": "manifest_write_failed"},
            )
        original_save_manifest(self, manifest)

    monkeypatch.setattr(FileRunStore, "save_manifest", failing_save_manifest)

    try:
        dataset = fo.Dataset(dataset_name)
        sample_id = dataset.add_sample(_sample(_write_source_image(tmp_path, "source")))

        with pytest.raises(MediaIOError):
            execute_fixed_augmentation(
                dataset=dataset,
                selected_sample_ids=(sample_id,),
                params={
                    "transform": "HorizontalFlip",
                    "p": 1.0,
                    "outputs_per_sample": 1,
                    "dry_run": False,
                },
                storage_root=tmp_path / "plugin-storage",
            )

        assert len(dataset) == 1
        assert _output_samples(dataset) == []
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
