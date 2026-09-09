from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config, create_fixed_image_pipeline
from albumentationsx_plugin.core import PipelineConfig, PipelinePreset, RunManifest, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    annotation_field_param_name,
    selected_annotation_fields_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.augmentation import FixedAugmentationExecutionResult
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    draft_parameter_group_name,
    flatten_fiftyone_form_groups,
    stage_parameter_group_name,
)
from albumentationsx_plugin.hosts.fiftyone.operators import augment as augment_module
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import (
    DRAFT_ID,
    LOAD_BUTTON,
    LOAD_NOTICE,
    LOAD_SOURCE,
    load_pipeline_draft,
    pipeline_draft_prompt_params,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import save_pipeline_preset_from_params
from albumentationsx_plugin.storage import FilePipelinePresetStore, FileRunStore

pytestmark = pytest.mark.unit


def _dataset(name="loading", **fields):
    schema = fields or {
        "boxes": fo.Detections,
        "masks": fo.Segmentation,
        "joints": fo.Keypoints,
        "category": fo.Classification,
    }
    return SimpleNamespace(
        name=name,
        media_type="image",
        get_field_schema=lambda: {key: fo.EmbeddedDocumentField(label_type) for key, label_type in schema.items()},
    )


def _sources(tmp_path, dataset):
    params = {
        "transform": "HorizontalFlip",
        "p": 1.0,
        "outputs_per_sample": 2,
        "save_preset_name": "Flip",
        "selected_label_fields": ["boxes", "masks", "category"],
    }
    preset = save_pipeline_preset_from_params(params, dataset=dataset, storage_root=tmp_path).preset
    manifest = RunManifest(
        run_key="flip-run",
        plugin_version="0.1.0",
        dependency_versions={},
        pipeline=replace(preset.pipeline, seed=123),
        metadata={"annotations": preset.metadata["annotation_selection"]},
        replay_records=({"saved_replay": True},),
    )
    FileRunStore(dataset.name, storage_root=tmp_path).save_manifest(manifest)
    return {"saved": f"saved:{preset.key}", "run": f"run:{manifest.run_key}"}


@pytest.mark.parametrize("kind", ["saved", "run"])
@pytest.mark.parametrize("preview", [False, True])
def test_loaded_edits_control_actual_execution(monkeypatch, tmp_path, kind, preview):
    dataset = _dataset()
    source = _sources(tmp_path, dataset)[kind]
    current = {"run_label": "new-run", "preview_only": preview, "_storage_root": str(tmp_path)}
    draft = load_pipeline_draft(dataset, source, current, storage_root=tmp_path)
    assert selected_annotation_fields_from_params(draft, dataset).selected_field_names == ("boxes", "masks", "category")
    # Browser edits live in nested groups. They must beat the flat initial values.
    draft[stage_parameter_group_name(1)] = {"p": 0.0}
    context = SimpleNamespace(dataset=dataset, view=object(), selected=("source-1",), params=draft)
    calls = []

    def execute(**kwargs):
        effective = kwargs["params"]
        calls.append(effective)
        pipeline = build_fixed_pipeline_config(effective)
        assert pipeline.transforms[0].params["p"] == 0.0
        assert pipeline.seed is None
        pixels = np.arange(60, dtype=np.uint8).reshape((4, 5, 3))
        np.testing.assert_array_equal(create_fixed_image_pipeline(pipeline).apply(pixels).image, pixels)
        assert effective["run_label"] == "new-run"
        assert "joints" not in selected_annotation_fields_from_params(effective, dataset).selected_field_names
        return FixedAugmentationExecutionResult(
            run_key="fresh-run",
            processed_count=1,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=False,
            output_tag="test",
            output_dir="/tmp/test",
        )

    monkeypatch.setattr(
        augment_module, "_execute_fixed_augmentation_preview" if preview else "_execute_fixed_augmentation", execute
    )
    # Execution must no longer require the source to exist, even for a queued job.
    if kind == "saved":
        FilePipelinePresetStore(storage_root=tmp_path).preset_path("flip").unlink()
    else:
        FileRunStore(dataset.name, storage_root=tmp_path).manifest_path("flip-run").unlink()
    result = augment_module.AugmentWithAlbumentationsX().execute(context)
    assert result["error_count"] == 0
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["saved", "run"])
def test_load_and_reload_replace_stages_but_keep_execution_settings(tmp_path, kind):
    dataset = _dataset()
    source = _sources(tmp_path, dataset)[kind]
    current = {
        "transform": "RandomCrop",
        "height": 9,
        "step_9_transform": "VerticalFlip",
        "_stage_parameters_1": {"width": 7},
        "_annotation_fields": {annotation_field_param_name("joints"): True},
        "selected_label_fields": ["joints"],
        "previous_run_key": "legacy",
        "seed": 123,
        "run_label": "keep",
        "execution_scope": "entire_dataset",
        "dry_run": True,
        "outputs_per_sample": 3,
    }
    draft = load_pipeline_draft(dataset, source, current, storage_root=tmp_path)
    assert draft["transform"] == "HorizontalFlip"
    assert draft["outputs_per_sample"] == 2
    assert draft["run_label"] == "keep"
    assert draft["execution_scope"] == "entire_dataset"
    assert draft["dry_run"] is True
    assert not {
        "height",
        "width",
        "step_9_transform",
        "selected_label_fields",
        "previous_run_key",
        "seed",
    }.intersection(draft)
    draft.update(
        {
            "pipeline_step_count": 2,
            "transform": "VerticalFlip",
            "pipeline_stage_order": 2,
            "step_2_transform": "HorizontalFlip",
            "step_2_pipeline_stage_order": 1,
            "step_2_p": 0.0,
        }
    )
    config = build_fixed_pipeline_config(draft)
    assert [(t.name, t.params["p"]) for t in config.transforms] == [("HorizontalFlip", 0.0), ("VerticalFlip", 1.0)]
    reloaded = load_pipeline_draft(dataset, source, draft, storage_root=tmp_path)
    assert reloaded["pipeline_step_count"] == 1
    assert reloaded["transform"] == "HorizontalFlip"
    assert reloaded["p"] == 1.0
    assert "step_2_transform" not in reloaded
    reloaded[annotation_field_param_name("joints")] = True
    assert "joints" in selected_annotation_fields_from_params(reloaded, dataset).selected_field_names


def test_cross_dataset_mapping_requires_matching_name_and_type(tmp_path):
    source = _sources(tmp_path, _dataset())["saved"]
    target = _dataset("another", boxes=fo.Classification, masks=fo.Segmentation, extra=fo.Keypoints)
    draft = load_pipeline_draft(target, source, {}, storage_root=tmp_path)
    assert selected_annotation_fields_from_params(draft, target).selected_field_names == ("masks",)
    assert "boxes (type changed: detections → classification)" in str(draft[LOAD_NOTICE])
    assert "category (missing or unsupported)" in str(draft[LOAD_NOTICE])
    assert "matched by field name and label type" in str(draft[LOAD_NOTICE])


def test_legacy_pipeline_without_selection_does_not_enable_every_field(tmp_path):
    preset = PipelinePreset(
        key="legacy",
        name="Legacy",
        pipeline=PipelineConfig(transforms=(TransformConfig("HorizontalFlip", {"p": 1}),)),
        plugin_version="0.1.0",
        dependency_versions={},
    )
    FilePipelinePresetStore(storage_root=tmp_path).save_preset(preset)
    dataset = _dataset()
    draft = load_pipeline_draft(dataset, "saved:legacy", {}, storage_root=tmp_path)
    assert selected_annotation_fields_from_params(draft, dataset).selected_field_names == ()
    assert "no annotation selection" in str(draft[LOAD_NOTICE])


def test_legacy_run_restores_target_and_copy_fields_without_new_annotations(tmp_path):
    dataset = _dataset()
    manifest = RunManifest(
        run_key="legacy",
        plugin_version="0.1.0",
        dependency_versions={},
        pipeline=PipelineConfig(
            transforms=(TransformConfig("HorizontalFlip", {"p": 1}),),
            target_fields=("boxes", "masks"),
            copy_fields=("category",),
        ),
    )
    FileRunStore(dataset.name, storage_root=tmp_path).save_manifest(manifest)
    draft = load_pipeline_draft(dataset, "run:legacy", {}, storage_root=tmp_path)
    assert selected_annotation_fields_from_params(draft, dataset).selected_field_names == ("boxes", "masks", "category")


def test_missing_source_leaves_form_draft_usable(tmp_path):
    params = {LOAD_SOURCE: "saved:missing", "transform": "HorizontalFlip", "p": 0.0, "_storage_root": str(tmp_path)}
    schema = (
        augment_module.AugmentWithAlbumentationsX()
        .resolve_input(SimpleNamespace(dataset=_dataset(), params=params))
        .to_json()["type"]["properties"]
    )
    assert LOAD_BUTTON not in schema
    assert "Current draft is unchanged" in schema["_pipeline_load_error"]["view"]["description"]
    assert schema[stage_parameter_group_name(1)]["type"]["properties"]["p"]["default"] == 0.0


@pytest.mark.parametrize("kind", ["saved", "run"])
def test_prompt_uses_nested_values_and_new_identity_only_on_explicit_reload(tmp_path, kind):
    dataset = _dataset()
    source = _sources(tmp_path, dataset)[kind]
    draft = load_pipeline_draft(dataset, source, {}, storage_root=tmp_path)
    params = cast(dict[str, Any], pipeline_draft_prompt_params(draft))
    group_name = draft_parameter_group_name(str(draft[DRAFT_ID]))
    values = params[group_name]
    assert values["_annotation_fields"][annotation_field_param_name("boxes")] is True
    assert values["_annotation_fields"][annotation_field_param_name("joints")] is False
    assert values["_stage_parameters_1"] == {"pipeline_stage_enabled": True, "pipeline_stage_order": 1, "p": 1.0}
    assert "p" not in values
    operator = augment_module.AugmentWithAlbumentationsX()
    ctx = SimpleNamespace(dataset=dataset, params=params)
    first = operator.resolve_input(ctx).to_json()
    assert first["view"]["componentsProps"]["container"]["key"] == draft[DRAFT_ID]
    values["_stage_parameters_1"]["p"] = 0.0
    edited = operator.resolve_input(ctx).to_json()
    assert edited["view"]["componentsProps"]["container"]["key"] == draft[DRAFT_ID]
    replacement = edited["type"]["properties"][group_name]["type"]["properties"][LOAD_BUTTON]["view"]["params"]
    assert replacement[DRAFT_ID] != draft[DRAFT_ID]
    new_values = replacement[draft_parameter_group_name(replacement[DRAFT_ID])]
    assert new_values["_stage_parameters_1"]["p"] == 1.0
    # Late default initialization from the replaced form must not overwrite the
    # active snapshot, including false checkboxes and a user's p=0 edit.
    params["_annotation_fields"] = {annotation_field_param_name("joints"): True}
    params["_stage_parameters_1"] = {"p": 1.0}
    params[draft_parameter_group_name("old")] = {"p": 1.0, annotation_field_param_name("joints"): True}
    effective = flatten_fiftyone_form_groups(params)
    assert effective["p"] == 0.0
    assert effective[annotation_field_param_name("joints")] is False


def test_explicitly_empty_annotation_selection_round_trips(tmp_path):
    dataset = _dataset()
    preset = save_pipeline_preset_from_params(
        {"transform": "HorizontalFlip", "save_preset_name": "No labels", "selected_label_fields": []},
        dataset=dataset,
        storage_root=tmp_path,
    ).preset
    draft = load_pipeline_draft(dataset, f"saved:{preset.key}", {}, storage_root=tmp_path)
    assert selected_annotation_fields_from_params(draft, dataset).selected_field_names == ()
    assert draft[LOAD_NOTICE] == ""


def test_complex_parameter_is_rendered_as_editable_json(tmp_path):
    dataset = _dataset()
    preset = save_pipeline_preset_from_params(
        {
            "transform": "RandomCrop",
            "height": 12,
            "width": 10,
            "fill": [1, 2, 3],
            "save_preset_name": "Crop",
            "selected_label_fields": [],
        },
        dataset=dataset,
        storage_root=tmp_path,
    ).preset
    draft = load_pipeline_draft(dataset, f"saved:{preset.key}", {}, storage_root=tmp_path)
    prompt = cast(dict[str, Any], pipeline_draft_prompt_params(draft))
    assert prompt[draft_parameter_group_name(str(draft[DRAFT_ID]))]["_stage_parameters_1"]["fill"] == "[1, 2, 3]"
