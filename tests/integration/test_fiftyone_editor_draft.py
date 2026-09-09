from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config
from albumentationsx_plugin.hosts.fiftyone.annotations import annotation_field_param_name
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    DRAFT_DATASET,
    EDITOR_ACTION,
    EDITOR_DRAFT,
    RESULT_DETAILS,
    RETURN_ERRORS,
    REVIEWED_SELECTION,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import DRAFT_ID, flatten_fiftyone_form_groups
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import pipeline_draft_prompt_params
from albumentationsx_plugin.hosts.fiftyone.samples import SOURCE_SAMPLE_ID_FIELD
from albumentationsx_plugin.storage import FilePipelinePresetStore, FileRunStore
from albumentationsx_plugin.storage.images import load_rgb_image, write_rgb_image

pytestmark = pytest.mark.integration


@pytest.fixture
def editor_context(tmp_path):
    pixels = np.arange(180, dtype=np.uint8).reshape((6, 10, 3))
    path = write_rgb_image(pixels, tmp_path, "source.png")
    dataset = fo.Dataset(f"editor-draft-{uuid4().hex}")
    try:
        ids = cast(
            list[str],
            dataset.add_samples(
                [
                    fo.Sample(
                        filepath=str(path),
                        boxes=fo.Detections(
                            detections=[fo.Detection(label="object", bounding_box=[0.1, 0.2, 0.3, 0.4])]
                        ),
                        ignored=fo.Classification(label="omit"),
                    )
                    for _ in range(2)
                ]
            ),
        )
        yield (
            SimpleNamespace(dataset=dataset, view=dataset, selected=[ids[0]], params={}),
            pixels,
            ids,
            tmp_path / "runs",
        )
    finally:
        dataset.delete()


def _return_params(operator, ctx, result, button="_back_to_editor"):
    ctx.results = result
    prop = operator.resolve_output(ctx).to_json()["type"]["properties"][button]
    assert prop["view"]["prompt"] is True
    return prop["view"]["params"]


def test_preview_return_creation_preserves_order_parameters_annotations_and_outputs(editor_context):
    ctx, pixels, ids, root = editor_context
    operator = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "preview",
        "pipeline_step_count": 2,
        "transform": "HorizontalFlip",
        "_stage_parameters_1": {"p": 1.0, "pipeline_stage_order": 2, "pipeline_stage_enabled": True},
        "step_2_transform": "VerticalFlip",
        "_stage_parameters_2": {
            "step_2_p": 0.0,
            "step_2_pipeline_stage_order": 1,
            "step_2_pipeline_stage_enabled": True,
        },
        "_annotation_fields": {
            annotation_field_param_name("boxes"): True,
            annotation_field_param_name("ignored"): False,
        },
        "_run_options": {"run_label": "draft-roundtrip"},
        "outputs_per_sample": 2,
        "execution_scope": "selected_samples",
        REVIEWED_SELECTION: [ids[0]],
        "_storage_root": str(root),
    }
    original = flatten_fiftyone_form_groups(ctx.params)
    preview = operator.execute(ctx)
    assert preview["error_count"] == 0 and preview["preview_count"] == 1
    assert len(ctx.dataset) == 2 and not root.exists()
    schema = operator.resolve_output(SimpleNamespace(params=ctx.params, results=preview)).to_json()["type"][
        "properties"
    ]
    assert next(iter(schema)) == "preview_1_comparison_image"
    assert schema[RESULT_DETAILS]["view"]["componentsProps"]["grid"]["component"] == "details"
    restored = _return_params(operator, ctx, preview)
    flat = flatten_fiftyone_form_groups(restored)
    assert all(flat[key] == value for key, value in original.items() if key != REVIEWED_SELECTION)
    assert flat[DRAFT_ID] != cast(dict, preview[EDITOR_DRAFT])[DRAFT_ID]
    # Repeated previews use the same config; they never replace it with sampled replay parameters.
    ctx.params = restored
    again = operator.execute(ctx)
    assert again["error_count"] == 0
    ctx.params = _return_params(operator, ctx, again, "_create_from_draft")
    effective = flatten_fiftyone_form_groups(ctx.params)
    effective[REVIEWED_SELECTION] = [ids[0]]  # initial value supplied by the reopened App form
    ctx.params = pipeline_draft_prompt_params(effective)
    created = operator.execute(ctx)
    assert created["error_count"] == 0 and created["created_count"] == 2
    manifest = FileRunStore(ctx.dataset.name, storage_root=root).load_manifest(str(created["run_key"]))
    assert [(step.name, step.params["p"]) for step in manifest.pipeline.transforms] == [
        ("VerticalFlip", 0.0),
        ("HorizontalFlip", 1.0),
    ]
    assert manifest.pipeline.outputs_per_sample == 2 and manifest.pipeline.seed is None
    for output in ctx.dataset.exists(SOURCE_SAMPLE_ID_FIELD):
        assert output[SOURCE_SAMPLE_ID_FIELD] == ids[0] and output.ignored is None
        np.testing.assert_array_equal(load_rgb_image(output.filepath).data, pixels[:, ::-1])
    # Materialization also offers a return to the same editor, without a stored run overlay.
    after = flatten_fiftyone_form_groups(_return_params(operator, ctx, created))
    assert after["run_label"] == "draft-roundtrip"
    assert build_fixed_pipeline_config(after) == build_fixed_pipeline_config(effective)


def test_runtime_error_can_be_corrected_without_reentering_draft(editor_context):
    ctx, _, _, root = editor_context
    op = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "preview",
        "transform": "RandomCrop",
        "height": 9999,
        "width": 10,
        "p": 1.0,
        "run_label": "keep-label",
        "_storage_root": str(root),
        annotation_field_param_name("ignored"): False,
    }
    failed = op.execute(ctx)
    assert cast(int, failed["error_count"]) > 0
    restored = flatten_fiftyone_form_groups(_return_params(op, ctx, failed))
    assert restored["height"] == 9999 and restored["run_label"] == "keep-label"
    assert restored[RETURN_ERRORS]
    restored["height"] = 3
    ctx.params = pipeline_draft_prompt_params(restored)
    preview = op.execute(ctx)
    assert preview["error_count"] == 0 and RETURN_ERRORS not in cast(dict, preview[EDITOR_DRAFT])
    assert len(ctx.dataset) == 2 and not root.exists()


def test_selection_change_requires_review_and_never_expands_empty_selection(editor_context):
    ctx, _, ids, root = editor_context
    op = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "create",
        "transform": "HorizontalFlip",
        "p": 0.0,
        "execution_scope": "selected_samples",
        REVIEWED_SELECTION: [ids[0]],
        "_storage_root": str(root),
    }
    ctx.selected = [ids[1]]  # Same count, different identity must also be detected.
    failed = op.execute(ctx)
    assert cast(list, failed["errors"])[0]["code"] == "selection_changed"
    assert not root.exists()
    restored = flatten_fiftyone_form_groups(_return_params(op, ctx, failed))
    assert restored["execution_scope"] == "selected_samples"
    ctx.selected = []
    ctx.params = pipeline_draft_prompt_params(restored)
    empty = op.execute(ctx)
    assert cast(list, empty["errors"])[0]["code"] == "no_selected_samples"
    assert len(ctx.dataset) == 2
    ctx.selected = [ids[1]]
    restored[REVIEWED_SELECTION] = [ids[1]]
    ctx.params = pipeline_draft_prompt_params(restored)
    created = op.execute(ctx)
    assert created["created_count"] == 1
    assert ctx.dataset.exists(SOURCE_SAMPLE_ID_FIELD).first()[SOURCE_SAMPLE_ID_FIELD] == ids[1]


def test_save_action_and_retained_name_do_not_turn_preview_into_save(editor_context):
    ctx, _, _, root = editor_context
    op = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "save",
        "transform": "HorizontalFlip",
        "p": 0.0,
        "_save_options": {"save_preset_name": "My draft", "save_preset_description": "Keep this description"},
        "_storage_root": str(root),
    }
    saved = op.execute(ctx)
    assert saved["preset_name"] == "My draft" and len(ctx.dataset) == 2
    path = FilePipelinePresetStore(storage_root=root).preset_path(str(saved["preset_key"]))
    before = path.read_bytes()
    ctx.params = _return_params(op, ctx, saved, "_preview_again")
    preview = op.execute(ctx)
    assert preview["error_count"] == 0 and preview["preview_count"] == 1
    assert path.read_bytes() == before
    draft = cast(dict, preview[EDITOR_DRAFT])
    assert draft["save_preset_name"] == "My draft"
    assert draft["save_preset_description"] == "Keep this description"


def test_draft_dataset_boundary_survives_failed_return(editor_context):
    ctx, _, _, root = editor_context
    op = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "create",
        "transform": "HorizontalFlip",
        DRAFT_DATASET: "different-dataset",
        "_storage_root": str(root),
    }
    for _ in range(2):
        result = op.execute(ctx)
        assert cast(list, result["errors"])[0]["code"] == "draft_dataset_changed"
        ctx.params = _return_params(op, ctx, result)
    assert not root.exists()


def test_invalid_json_and_disabled_stage_are_preserved_by_snapshot(editor_context):
    ctx, _, _, root = editor_context
    op = AugmentWithAlbumentationsX()
    ctx.params = {
        EDITOR_ACTION: "preview",
        "pipeline_step_count": 2,
        "transform": "RandomCrop",
        "height": 2,
        "width": 2,
        "fill": "[broken",
        "step_2_transform": "VerticalFlip",
        "step_2_pipeline_stage_enabled": False,
        "step_2_p": 0.27,
        "_storage_root": str(root),
    }
    failed = op.execute(ctx)
    assert cast(int, failed["error_count"]) > 0
    restored = flatten_fiftyone_form_groups(_return_params(op, ctx, failed))
    assert restored["fill"] == "[broken" and restored["step_2_pipeline_stage_enabled"] is False
    assert restored["step_2_p"] == 0.27 and restored["pipeline_step_count"] == 2
    json.dumps(failed, allow_nan=False)


@pytest.mark.parametrize(
    "action,label,delegation",
    [
        ("preview", "Preview", False),
        ("save", "Save pipeline", False),
        ("validate", "Validate without creating samples", False),
        ("create", "Create augmented samples", None),
    ],
)
def test_action_labels_and_execution_choices(editor_context, action, label, delegation):
    ctx, _, _, _ = editor_context
    ctx.params = {EDITOR_ACTION: action, "save_preset_name": "Example"}
    op = AugmentWithAlbumentationsX()
    schema = op.resolve_input(ctx).to_json()
    assert schema["view"]["submit_button_label"] == label
    assert op.resolve_delegation(ctx) is delegation


def test_known_validation_blocks_submission_inside_editor(editor_context):
    ctx, _, _, _ = editor_context
    ctx.params = {"pipeline_step_count": 2, "pipeline_stage_order": 1, "step_2_pipeline_stage_order": 1}
    schema = AugmentWithAlbumentationsX().resolve_input(ctx).to_json()["type"]["properties"]
    assert schema["_augment_validation_warning"]["invalid"] is True
    assert "unique execution order" in schema["_augment_validation_warning"]["error_message"]


def test_app_output_uses_independent_modal_to_allow_return(editor_context):
    ctx, _, _, root = editor_context
    op = AugmentWithAlbumentationsX()
    events = []
    ctx.prompt_id = None  # Released App versions may omit this value.
    ctx.trigger = lambda name, **kwargs: events.append((name, kwargs))
    ctx.params = {EDITOR_ACTION: "preview", "transform": "HorizontalFlip", "p": 0.0, "_storage_root": str(root)}
    result = op.execute(ctx)
    assert result["error_count"] == 0 and result["_displayed_in_app"] is True
    assert len(events) == 1 and events[0][0] == "show_output"
    shown = events[0][1]["params"]
    assert shown["results"][EDITOR_DRAFT]["p"] == 0.0
    assert "_back_to_editor" in shown["outputs"]["type"]["properties"]
    ctx.results = result
    assert not op.resolve_output(ctx).type.properties


@pytest.mark.parametrize("action", ["unknown", []])
def test_unknown_ui_action_cannot_create_samples(editor_context, action):
    ctx, _, _, root = editor_context
    ctx.params = {EDITOR_ACTION: action, "transform": "HorizontalFlip", "_storage_root": str(root)}
    result = AugmentWithAlbumentationsX().execute(ctx)
    assert cast(list, result["errors"])[0]["code"] == "invalid_editor_action"
    assert len(ctx.dataset) == 2 and not root.exists()
