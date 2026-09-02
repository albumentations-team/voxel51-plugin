from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, cast

import fiftyone as fo
import pytest

from albumentationsx_plugin.core import (
    PIPELINE_STEP_COUNT_FIELD_NAME,
    RUN_EXECUTION_STATUS_PREVIEW,
    RUN_LABEL_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
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
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    PIPELINE_PRESET_KEY_FIELD_NAME,
    PRESET_SAVED_EXECUTION_STATUS,
    SAVE_PRESET_DESCRIPTION_FIELD_NAME,
    SAVE_PRESET_NAME_FIELD_NAME,
    SAVE_PRESET_ONLY_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.presets import PREVIOUS_RUN_KEY_FIELD_NAME, STORAGE_ROOT_PARAM_NAME
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    PREVIEW_FIELD_COMPARISON_IMAGE,
    PREVIEW_FIELD_OUTPUT_IMAGE,
    PREVIEW_ONLY_FIELD_NAME,
    preview_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import CLEANUP_STATUS_OK
from albumentationsx_plugin.hosts.fiftyone.run_summary import RUN_STATUS_OK
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG, SOURCE_SAMPLE_ID_FIELD
from albumentationsx_plugin.storage import FilePipelinePresetStore, FileRunStore
from scripts.create_demo_dataset import DEMO_SAMPLES, create_demo_dataset, delete_demo_dataset


class _OperatorContext:
    def __init__(
        self,
        *,
        dataset: fo.Dataset,
        params: dict[str, object],
        selected: tuple[str, ...] = (),
        view: Any | None = None,
    ) -> None:
        self.dataset = dataset
        self.view = dataset if view is None else view
        self.selected = selected
        self.params = params
        self.progress_events: list[dict[str, object]] = []
        self.triggers: list[tuple[str, dict[str, object]]] = []

    def set_progress(self, *, progress: float, label: str) -> None:
        self.progress_events.append({"progress": progress, "label": label})

    def trigger(self, operator_name: str, params: dict[str, object] | None = None) -> None:
        self.triggers.append((operator_name, {} if params is None else params))


def _dataset_name(suffix: str) -> str:
    return f"albumentationsx-demo-user-{suffix}-{uuid.uuid4().hex}"


def _load_sample(dataset: fo.Dataset, sample_id: str) -> Any:
    return cast(Any, dataset[sample_id])


@pytest.mark.integration
@pytest.mark.smoke
def test_demo_user_scenario_previews_runs_inspects_and_deletes_selected_samples(tmp_path) -> None:
    dataset_name = _dataset_name("selected")
    data_root = tmp_path / "demo-data" / dataset_name
    storage_root = tmp_path / "plugin-storage"

    try:
        create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        dataset = fo.load_dataset(dataset_name)
        source_samples = list(dataset)
        selected_sample_id = str(source_samples[0].id)
        source_filepaths = {str(sample.id): str(sample.filepath) for sample in source_samples}

        preview_context = _OperatorContext(
            dataset=dataset,
            selected=(selected_sample_id,),
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
                PREVIEW_ONLY_FIELD_NAME: True,
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
            },
        )
        preview = AugmentWithAlbumentationsX().execute(preview_context)

        assert preview["execution_status"] == RUN_EXECUTION_STATUS_PREVIEW
        assert preview["source_scope"] == EXECUTION_SCOPE_SELECTED_SAMPLES
        assert preview["processed_count"] == 1
        assert preview["preview_count"] == 1
        assert preview["created_count"] == 0
        assert preview["manifest_path"] == ""
        assert preview_context.triggers == []
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 0
        assert len(dataset) == len(DEMO_SAMPLES)
        assert str(preview[preview_field_name(1, PREVIEW_FIELD_OUTPUT_IMAGE)]).startswith("data:image/png;base64,")
        assert str(preview[preview_field_name(1, PREVIEW_FIELD_COMPARISON_IMAGE)]).startswith("data:image/png;base64,")

        run_context = _OperatorContext(
            dataset=dataset,
            selected=(selected_sample_id,),
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
                RUN_LABEL_FIELD_NAME: "Demo UI flow",
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
        )
        run = AugmentWithAlbumentationsX().execute(run_context)

        assert run["error_count"] == 0
        assert run["source_scope"] == EXECUTION_SCOPE_SELECTED_SAMPLES
        assert run["processed_count"] == 1
        assert run["created_count"] == 1
        assert str(run["run_key"]).startswith("demo-ui-flow-albumentationsx-")
        assert run_context.triggers == [("reload_dataset", {})]
        assert run_context.progress_events

        created = list(dataset.match_tags(DEFAULT_OUTPUT_TAG))
        assert len(created) == 1
        assert created[0].get_field(SOURCE_SAMPLE_ID_FIELD) == selected_sample_id
        assert Path(str(created[0].filepath)).exists()
        assert dataset.has_run(str(run["fiftyone_run_key"]))

        summary = ViewAlbumentationsXRun().execute(
            _OperatorContext(
                dataset=dataset,
                params={"run_key": str(run["run_key"]), VIEW_STORAGE_ROOT_PARAM: str(storage_root)},
            )
        )

        assert summary["status"] == RUN_STATUS_OK
        assert summary["created_count"] == 1
        assert summary["available_output_count"] == 1
        assert summary["replay_available"] is True
        assert json.loads(str(summary["generated_sample_ids_json"])) == [str(created[0].id)]

        delete_context = _OperatorContext(
            dataset=dataset,
            params={
                "run_key": str(run["run_key"]),
                CONFIRM_FIELD_NAME: True,
                DELETE_STORAGE_ROOT_PARAM: str(storage_root),
            },
        )
        cleanup = DeleteAlbumentationsXRun().execute(delete_context)

        assert cleanup["status"] == CLEANUP_STATUS_OK
        assert cleanup["deleted_sample_count"] == 1
        assert cleanup["deleted_file_count"] == 1
        assert delete_context.triggers == [("reload_dataset", {})]
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 0
        assert len(dataset) == len(DEMO_SAMPLES)
        assert not dataset.has_run(str(run["fiftyone_run_key"]))
        for sample_id, filepath in source_filepaths.items():
            assert str(_load_sample(dataset, sample_id).filepath) == filepath
            assert Path(filepath).exists()
    finally:
        delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)


@pytest.mark.integration
@pytest.mark.smoke
def test_demo_user_scenario_can_run_current_view_or_entire_dataset_scope(tmp_path) -> None:
    dataset_name = _dataset_name("scope")
    data_root = tmp_path / "demo-data" / dataset_name
    storage_root = tmp_path / "plugin-storage"

    try:
        create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        dataset = fo.load_dataset(dataset_name)
        train_view = dataset.match_tags("train")

        view_context = _OperatorContext(
            dataset=dataset,
            view=train_view,
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_CURRENT_VIEW,
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
        )
        view_run = AugmentWithAlbumentationsX().execute(view_context)

        assert view_run["error_count"] == 0
        assert view_run["source_scope"] == EXECUTION_SCOPE_CURRENT_VIEW
        assert view_run["processed_count"] == train_view.count()
        assert view_run["created_count"] == train_view.count()
        assert view_context.triggers == [("reload_dataset", {})]

        cleanup = DeleteAlbumentationsXRun().execute(
            _OperatorContext(
                dataset=dataset,
                params={
                    "run_key": str(view_run["run_key"]),
                    CONFIRM_FIELD_NAME: True,
                    DELETE_STORAGE_ROOT_PARAM: str(storage_root),
                },
            )
        )
        assert cleanup["status"] == CLEANUP_STATUS_OK
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 0

        entire_context = _OperatorContext(
            dataset=dataset,
            view=train_view,
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_ENTIRE_DATASET,
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
        )
        entire_run = AugmentWithAlbumentationsX().execute(entire_context)

        assert entire_run["error_count"] == 0
        assert entire_run["source_scope"] == EXECUTION_SCOPE_ENTIRE_DATASET
        assert entire_run["processed_count"] == len(DEMO_SAMPLES)
        assert entire_run["created_count"] == len(DEMO_SAMPLES)
        assert entire_context.triggers == [("reload_dataset", {})]

        run_store = FileRunStore(dataset.name, storage_root=storage_root)
        view_manifest = run_store.load_manifest(str(view_run["run_key"]))
        entire_manifest = run_store.load_manifest(str(entire_run["run_key"]))
        assert view_manifest.metadata[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_CURRENT_VIEW
        assert entire_manifest.metadata[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_ENTIRE_DATASET
    finally:
        delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)


@pytest.mark.integration
@pytest.mark.smoke
def test_demo_user_scenario_saves_named_preset_and_reuses_previous_run(tmp_path) -> None:
    dataset_name = _dataset_name("reuse")
    data_root = tmp_path / "demo-data" / dataset_name
    storage_root = tmp_path / "plugin-storage"

    try:
        create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        dataset = fo.load_dataset(dataset_name)
        source_ids = tuple(str(sample.id) for sample in dataset)
        operator = AugmentWithAlbumentationsX()

        save_context = _OperatorContext(
            dataset=dataset,
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                SAVE_PRESET_ONLY_FIELD_NAME: True,
                SAVE_PRESET_NAME_FIELD_NAME: "Reusable demo flip",
                SAVE_PRESET_DESCRIPTION_FIELD_NAME: "Headless user scenario preset.",
                "transform": "HorizontalFlip",
                "p": 1.0,
                "outputs_per_sample": 2,
            },
        )
        saved = operator.execute(save_context)

        assert saved["execution_status"] == PRESET_SAVED_EXECUTION_STATUS
        assert saved["created_count"] == 0
        assert saved["preset_key"] == "reusable-demo-flip"
        assert save_context.triggers == []
        preset = FilePipelinePresetStore(storage_root=storage_root).load_preset(str(saved["preset_key"]))
        assert preset.pipeline.outputs_per_sample == 2
        assert [transform.name for transform in preset.pipeline.transforms] == ["HorizontalFlip"]

        preset_context = _OperatorContext(
            dataset=dataset,
            selected=(source_ids[0],),
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                PIPELINE_PRESET_KEY_FIELD_NAME: str(saved["preset_key"]),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
            },
        )
        preset_run = operator.execute(preset_context)

        assert preset_run["error_count"] == 0
        assert preset_run["created_count"] == 2
        assert preset_context.triggers == [("reload_dataset", {})]

        previous_run_context = _OperatorContext(
            dataset=dataset,
            selected=(source_ids[1],),
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                PREVIOUS_RUN_KEY_FIELD_NAME: str(preset_run["run_key"]),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
            },
        )
        previous_run = operator.execute(previous_run_context)

        assert previous_run["error_count"] == 0
        assert previous_run["created_count"] == 2
        assert previous_run["run_key"] != preset_run["run_key"]
        assert previous_run_context.triggers == [("reload_dataset", {})]

        run_store = FileRunStore(dataset.name, storage_root=storage_root)
        preset_manifest = run_store.load_manifest(str(preset_run["run_key"]))
        previous_manifest = run_store.load_manifest(str(previous_run["run_key"]))
        assert preset_manifest.pipeline.transforms == previous_manifest.pipeline.transforms
        assert preset_manifest.pipeline.outputs_per_sample == previous_manifest.pipeline.outputs_per_sample
        assert previous_manifest.source_sample_ids == (source_ids[1],)
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 4
    finally:
        delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)


@pytest.mark.integration
@pytest.mark.smoke
def test_demo_user_scenario_reports_validation_error_with_config_diagnostics(tmp_path) -> None:
    dataset_name = _dataset_name("diagnostics")
    data_root = tmp_path / "demo-data" / dataset_name
    storage_root = tmp_path / "plugin-storage"

    try:
        create_demo_dataset(
            dataset_name=dataset_name,
            data_root=data_root,
            samples=(DEMO_SAMPLES[0],),
        )
        dataset = fo.load_dataset(dataset_name)
        sample_id = str(next(iter(dataset)).id)
        context = _OperatorContext(
            dataset=dataset,
            selected=(sample_id,),
            params={
                STORAGE_ROOT_PARAM_NAME: str(storage_root),
                EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
                PIPELINE_STEP_COUNT_FIELD_NAME: 2,
                "transform": "HorizontalFlip",
                "p": 1.0,
                "step_2_transform": "RandomBrightnessContrast",
                "step_2_brightness_range": [-0.2, 0.2],
                "step_2_contrast_range": [-0.2, 0.2],
                "step_2_p": 1.0,
                "outputs_per_sample": 1,
                "dry_run": False,
            },
        )

        result = AugmentWithAlbumentationsX().execute(context)

        assert result["created_count"] == 0
        assert result["error_count"] == 1
        assert context.triggers == []
        assert dataset.match_tags(DEFAULT_OUTPUT_TAG).count() == 0
        errors = json.loads(str(result["errors_json"]))
        pipeline_config = json.loads(str(result["pipeline_config_json"]))
        operator_params = json.loads(str(result["operator_params_json"]))
        assert errors[0]["code"] == "host_adapter_error"
        assert errors[0]["context"]["reason"] == "annotation_target_incompatible"
        assert pipeline_config["transforms"][1]["name"] == "RandomBrightnessContrast"
        assert operator_params["step_2_transform"] == "RandomBrightnessContrast"
    finally:
        delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)
