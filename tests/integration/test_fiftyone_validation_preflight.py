from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.hosts.fiftyone.editor_draft import EDITOR_ACTION
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = pytest.mark.integration


@pytest.fixture
def validation_context(tmp_path):
    path = write_rgb_image(np.zeros((8, 10, 3), dtype=np.uint8), tmp_path, "source.png")
    dataset = fo.Dataset(f"vox-73-validation-{uuid4().hex}")
    try:
        sample_id = dataset.add_sample(fo.Sample(filepath=str(path), metadata=fo.ImageMetadata(width=10, height=8)))
        root = tmp_path / "outputs"
        yield SimpleNamespace(dataset=dataset, view=dataset, selected=[sample_id], params={}), root, path
    finally:
        dataset.delete()


def _properties(schema):
    result = {}
    for name, prop in schema["type"]["properties"].items():
        result[name] = prop
        if prop["type"]["name"] == "Object":
            result.update(_properties(prop))
    return result


@pytest.mark.parametrize("action", ["preview", "validate", "create", "delegated", "save"])
@pytest.mark.parametrize("invalid", ["order", "probability", "json", "no_stages"])
def test_invalid_configuration_matrix_has_field_errors_and_no_side_effects(validation_context, action, invalid):
    ctx, root, path = validation_context
    before = path.read_bytes()
    ctx.delegated = action == "delegated"
    ctx.params = {
        EDITOR_ACTION: "create" if ctx.delegated else action,
        "transform": "HorizontalFlip",
        "p": 1.0,
        "save_preset_name": "matrix",
        "_storage_root": str(root),
    }
    changes = {
        "order": {"pipeline_step_count": 2, "step_2_pipeline_stage_order": 1},
        "probability": {"p": 2.0},
        "json": {"transform": "Affine", "translate_percent": "{invalid"},
        "no_stages": {"pipeline_stage_enabled": False},
    }
    ctx.params.update(changes[invalid])
    op = AugmentWithAlbumentationsX()
    fields = _properties(op.resolve_input(ctx).to_json())
    assert fields["_augment_validation_warning"]["invalid"]
    assert any(prop["invalid"] for name, prop in fields.items() if not name.startswith("_augment_validation"))
    result = cast(dict[str, Any], op.execute(ctx))
    assert result["error_count"] > 0
    assert len(ctx.dataset) == 1 and ctx.dataset.list_runs() == []
    assert not root.exists() and path.read_bytes() == before


@pytest.mark.parametrize("action", ["preview", "validate", "create", "delegated"])
def test_oversized_crop_fails_before_writes_and_recovers(validation_context, action):
    ctx, root, path = validation_context
    ctx.delegated = action == "delegated"
    ctx.params = {
        EDITOR_ACTION: "create" if ctx.delegated else action,
        "transform": "RandomCrop",
        "height": 9999,
        "width": 10,
        "p": 1.0,
        "_storage_root": str(root),
    }
    op = AugmentWithAlbumentationsX()
    fields = _properties(op.resolve_input(ctx).to_json())
    assert fields["height"]["invalid"] and "9999" in fields["height"]["error_message"]
    result = cast(dict[str, Any], op.execute(ctx))
    assert result["error_count"] > 0 and result["created_count"] == 0
    assert result["errors"][0]["context"]["sample_id"] == ctx.selected[0]
    assert len(ctx.dataset) == 1 and ctx.dataset.list_runs() == [] and not root.exists()
    ctx.params["height"] = 4
    assert not _properties(op.resolve_input(ctx).to_json())["height"]["invalid"]
    recovered = op.execute(ctx)
    assert recovered["error_count"] == 0
    if action in {"preview", "validate"}:
        assert not root.exists() and ctx.dataset.list_runs() == []
    else:
        assert recovered["created_count"] == 1


def test_dry_run_reads_media_even_without_metadata(validation_context):
    ctx, root, path = validation_context
    sample = ctx.dataset.first()
    sample.metadata = None
    sample.save()
    path.write_bytes(b"broken image")
    ctx.params = {EDITOR_ACTION: "validate", "_storage_root": str(root)}
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["error_count"] == 1
    assert result["errors"][0]["code"] == "io_error"
    assert not root.exists() and ctx.dataset.list_runs() == []


def test_selection_name_and_disabled_stage_validation_recover(validation_context):
    ctx, root, _ = validation_context
    op = AugmentWithAlbumentationsX()
    ctx.selected = []
    ctx.params = {EDITOR_ACTION: "preview", "_storage_root": str(root)}
    assert _properties(op.resolve_input(ctx).to_json())["execution_scope"]["invalid"]
    ctx.params[EDITOR_ACTION] = "save"
    assert _properties(op.resolve_input(ctx).to_json())["save_preset_name"]["invalid"]
    ctx.params = {
        **ctx.params,
        **dict(
            save_preset_name="Valid",
            pipeline_step_count=2,
            step_2_transform="RandomCrop",
            step_2_height=-1,
            step_2_pipeline_stage_enabled=False,
            step_2_pipeline_stage_order=1,
        ),
    }
    fields = _properties(op.resolve_input(ctx).to_json())
    assert "_augment_validation_warning" not in fields
    assert not fields["save_preset_name"]["invalid"]
    assert op.execute(ctx)["error_count"] == 0


@pytest.mark.parametrize(
    "mode",
    [
        {"preview_only": True, "dry_run": True},
        {"save_preset_only": True, "preview_only": True},
        {"save_preset_only": True},
    ],
)
def test_invalid_legacy_modes_never_write(validation_context, mode):
    ctx, root, _ = validation_context
    ctx.params = {**mode, "_storage_root": str(root)}
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["error_count"] > 0 and not root.exists()
    assert ctx.dataset.list_runs() == []


def test_preflight_checks_all_sources_before_creating_a_run(validation_context, tmp_path):
    ctx, root, _ = validation_context
    small = write_rgb_image(np.zeros((2, 2, 3), dtype=np.uint8), tmp_path, "small.png")
    small_id = ctx.dataset.add_sample(fo.Sample(filepath=str(small)))
    ctx.params = {
        EDITOR_ACTION: "create",
        "execution_scope": "current_view",
        "transform": "RandomCrop",
        "height": 4,
        "width": 4,
        "p": 1.0,
        "_storage_root": str(root),
    }
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["errors"][0]["context"]["sample_id"] == small_id
    assert result["created_count"] == 0 and len(ctx.dataset) == 2
    assert ctx.dataset.list_runs() == [] and not root.exists()


def test_dry_run_applies_stages_beyond_static_shape_inference(validation_context):
    ctx, root, _ = validation_context
    ctx.params = {
        EDITOR_ACTION: "validate",
        "pipeline_step_count": 2,
        "transform": "CenterCrop",
        "height": 4,
        "width": 4,
        "p": 1.0,
        "step_2_transform": "RandomCrop",
        "step_2_height": 8,
        "step_2_width": 8,
        "step_2_p": 1.0,
        "_storage_root": str(root),
    }
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["error_count"] == 1
    assert result["errors"][0]["context"]["reason_code"] == "albumentations_runtime_error"
    assert result["errors"][0]["context"]["sample_id"] == ctx.selected[0]
    assert not root.exists() and ctx.dataset.list_runs() == []


def test_inline_crop_validation_resolves_app_selection_descriptors(validation_context):
    ctx, _, _ = validation_context
    ctx.selected_samples = [{"id": ctx.selected[0]}]
    ctx.params = {EDITOR_ACTION: "preview", "transform": "RandomCrop", "height": 9999, "width": 4, "p": 1.0}
    fields = _properties(AugmentWithAlbumentationsX().resolve_input(ctx).to_json())
    assert fields["height"]["invalid"]
    assert "9999" in fields["height"]["error_message"]
    assert fields["height"]["view"]["componentsProps"]["field"]["autoFocus"]


def test_legacy_save_and_create_preflights_before_persisting_preset(validation_context):
    ctx, root, _ = validation_context
    ctx.params = {
        "transform": "RandomCrop",
        "height": 9999,
        "width": 4,
        "p": 1.0,
        "save_preset_name": "preflighted",
        "_storage_root": str(root),
    }
    op = AugmentWithAlbumentationsX()
    failed = op.execute(ctx)
    assert failed["error_count"] == 1 and not root.exists()
    assert ctx.dataset.list_runs() == [] and len(ctx.dataset) == 1
    ctx.params["height"] = 4
    created = op.execute(ctx)
    assert created["created_count"] == 1 and created["error_count"] == 0
    assert created["preset_name"] == "preflighted"
