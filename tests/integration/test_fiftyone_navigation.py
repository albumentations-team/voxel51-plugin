from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config
from albumentationsx_plugin.core import MediaIOError
from albumentationsx_plugin.hosts.fiftyone.cleanup_preview import build_cleanup_preview
from albumentationsx_plugin.hosts.fiftyone.editor_draft import EDITOR_ACTION
from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_fiftyone_form_groups
from albumentationsx_plugin.hosts.fiftyone.operators import (
    AnalyzeAlbumentationsXCompatibility,
    AugmentWithAlbumentationsX,
    DeleteAlbumentationsXRun,
    ManageAlbumentationsXPresets,
    ShowAlbumentationsXCapabilities,
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import pipeline_draft_prompt_params
from albumentationsx_plugin.hosts.fiftyone.run_library import list_run_library
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = pytest.mark.integration


@pytest.fixture
def navigation_context(tmp_path):
    path = write_rgb_image(np.arange(720, dtype=np.uint8).reshape(12, 20, 3), tmp_path, "source.png")
    dataset = fo.Dataset(f"vox75-navigation-{uuid4().hex}")
    try:
        ids = dataset.add_samples([fo.Sample(filepath=str(path), tags=["source"]) for _ in range(2)])
        events = []
        ctx = SimpleNamespace(
            dataset=dataset,
            view=dataset.match_tags("source"),
            selected=ids,
            params={
                "transform": "HorizontalFlip",
                "p": 0.0,
                "run_label": "First navigation run",
                "_storage_root": str(tmp_path / "runs"),
                EDITOR_ACTION: "create",
            },
            trigger=lambda name, params=None: events.append((name, params)),
        )
        yield ctx, path, events
    finally:
        dataset.delete()


def _fields(schema):
    result = {}
    for name, prop in schema["type"]["properties"].items():
        result[name] = prop
        if prop["type"]["name"] == "Object":
            result.update(_fields(prop))
    return result


def test_three_primary_entries_preserve_all_operator_uris(navigation_context):
    ctx, _, _ = navigation_context
    operators = [
        AugmentWithAlbumentationsX(),
        ManageAlbumentationsXPresets(),
        ViewAlbumentationsXRun(),
        AnalyzeAlbumentationsXCompatibility(),
        ShowAlbumentationsXCapabilities(),
        DeleteAlbumentationsXRun(),
    ]
    assert len({op.config.name for op in operators}) == 6
    visible = [op for op in operators if not op.config.unlisted]
    assert all(op.resolve_placement(ctx) is None for op in operators)
    assert [op.config.label for op in visible] == [
        "AlbumentationsX · Augment images",
        "AlbumentationsX · Saved pipelines",
        "AlbumentationsX · Run history",
    ]
    assert [op.config.unlisted for op in operators] == [False, False, False, True, True, True]
    assert ViewAlbumentationsXRun().config.risk_level.value == "low"


def test_discovery_and_compatibility_preserve_draft_and_execution(navigation_context):
    ctx, _, _ = navigation_context
    ctx.params.update({"transform": "RandomBrightnessContrast", "p": 0.0, "_stage_target_1": "bboxes"})
    pipeline = build_fixed_pipeline_config(ctx.params)
    for target in ["bboxes", "image", "all"]:
        ctx.params["_stage_target_1"] = target
        fields = _fields(AugmentWithAlbumentationsX().resolve_input(ctx).to_json())
        choices = fields["transform"]["type"]["values"]
        assert "RandomBrightnessContrast" in choices  # Filtering cannot silently replace the selected stage.
        assert fields["transform"]["default"] == "RandomBrightnessContrast"
        assert fields["p"]["default"] == 0.0
        assert "_compatibility_details" in fields
        assert build_fixed_pipeline_config(ctx.params) == pipeline
    snapshot = {**ctx.params, "_pipeline_draft_id": "navigation-test"}
    assert flatten_fiftyone_form_groups(pipeline_draft_prompt_params(snapshot))["_stage_target_1"] == "all"


def test_create_history_reuse_cleanup_flow_preserves_sources(navigation_context):
    ctx, source, events = navigation_context
    original = source.read_bytes()
    op = AugmentWithAlbumentationsX()
    result = cast(dict[str, Any], op.execute(ctx))
    assert result["created_count"] == 2
    # Automatic result navigation is built from the dataset, clearing source filters.
    view_event = next(params for name, params in events if name == "set_view")
    assert len(view_event["view"]) == 1
    assert "Select" in view_event["view"][0]["_cls"]
    root = ctx.params["_storage_root"]
    store = FileRunStore(ctx.dataset.name, storage_root=root)
    manifest = store.load_manifest(result["run_key"])
    assert set(view_event["view"][0]["kwargs"][0][1]) == set(manifest.created_sample_ids)
    ctx.params = {"run_key": result["run_key"], "_storage_root": root}
    history = ViewAlbumentationsXRun()
    fields = _fields(history.resolve_input(ctx).to_json())
    assert "First navigation run" in fields["run_details"]["view"]["label"]
    assert fields["_open_generated_samples"]["view"]["params"]["run_key"] == result["run_key"]
    ctx.params = fields["_load_pipeline"]["view"]["params"]
    draft = flatten_fiftyone_form_groups(ctx.params)
    assert draft["p"] == 0.0 and "previous_run_key" not in draft
    draft.update({"p": 1.0, EDITOR_ACTION: "create", "run_label": "Repeat navigation run"})
    ctx.params = pipeline_draft_prompt_params(draft)
    repeat = cast(dict[str, Any], op.execute(ctx))
    assert store.load_manifest(result["run_key"]).pipeline.transforms[0].params["p"] == 0.0
    assert store.load_manifest(repeat["run_key"]).pipeline.transforms[0].params["p"] == 1.0
    for run in (result, repeat):
        ctx.params = {"run_key": run["run_key"], "_storage_root": root}
        fields = _fields(history.resolve_input(ctx).to_json())
        ctx.params = fields["delete_run_outputs"]["view"]["params"]
        preview = build_cleanup_preview(ctx.dataset, run["run_key"], storage_root=root)
        assert preview.sample_count == preview.file_count == 2
        cleanup = DeleteAlbumentationsXRun()
        confirm = f"_confirm_run_{run['run_key']}"
        schema = _fields(cleanup.resolve_input(ctx).to_json())
        assert schema[confirm]["invalid"] is True
        assert cleanup.execute(ctx)["status"] == "confirmation_required"
        # A confirmation for another run cannot authorize this deletion.
        ctx.params["_confirm_run_another-run"] = True
        assert cleanup.execute(ctx)["status"] == "confirmation_required"
        ctx.params[confirm] = True
        assert _fields(cleanup.resolve_input(ctx).to_json())[confirm]["invalid"] is False
        deleted = cleanup.execute(ctx)
        assert deleted["deleted_sample_count"] == deleted["deleted_file_count"] == 2
        assert source.read_bytes() == original
        assert (
            next(e for e in list_run_library(ctx.dataset, storage_root=root) if e.run_key == run["run_key"]).status
            == "cleaned"
        )
        ctx.params = {"run_key": run["run_key"], "_storage_root": root}
        fields = _fields(history.resolve_input(ctx).to_json())
        assert "delete_run_outputs" not in fields and "_load_pipeline" in fields
    assert len(ctx.dataset) == 2
    assert ctx.dataset.count_sample_tags() == {"source": 2}


def test_cleanup_preview_rejects_unsafe_paths_without_writing(navigation_context):
    ctx, source, _ = navigation_context
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    root = ctx.params["_storage_root"]
    store = FileRunStore(ctx.dataset.name, storage_root=root)
    path = store.manifest_path(result["run_key"])
    data = json.loads(path.read_text())
    data["output_paths"].append("../source.png")
    path.write_text(json.dumps(data))
    before = source.read_bytes()
    with pytest.raises(MediaIOError):
        build_cleanup_preview(ctx.dataset, result["run_key"], storage_root=root)
    ctx.params = {"run_key": result["run_key"], "_storage_root": root, "_history_run": True}
    fields = _fields(DeleteAlbumentationsXRun().resolve_input(ctx).to_json())
    assert fields["_cleanup_preview_error"]["invalid"] is True
    assert source.read_bytes() == before


def test_failed_history_navigates_to_correct_source(navigation_context):
    ctx, _, events = navigation_context
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    root = ctx.params["_storage_root"]
    store = FileRunStore(ctx.dataset.name, storage_root=root)
    manifest = store.load_manifest(result["run_key"])
    errors = ({"message": "Read failed", "code": "media_error", "context": {"sample_id": ctx.selected[0]}},)
    store.save_manifest(
        replace(
            manifest,
            errors=errors,
            counters={**manifest.counters, "errors": 1},
            metadata={**manifest.metadata, "execution_status": "partial"},
        )
    )
    ctx.params = {"run_key": result["run_key"], "_storage_root": root}
    fields = _fields(ViewAlbumentationsXRun().resolve_input(ctx).to_json())
    ctx.params = fields["_open_failed_samples"]["view"]["params"]
    events.clear()
    ViewAlbumentationsXRun().execute(ctx)
    assert events[0][0] == "set_view"
    assert events[0][1]["view"][0]["kwargs"][0][1] == [ctx.selected[0]]


def test_failed_automatic_navigation_keeps_successful_result(navigation_context, monkeypatch):
    from albumentationsx_plugin.hosts.fiftyone.operators import augment

    ctx, _, events = navigation_context

    def unavailable(*args):
        raise RuntimeError("App navigation unavailable")

    monkeypatch.setattr(augment, "_open_created_outputs", unavailable)
    result = AugmentWithAlbumentationsX().execute(ctx)
    assert result["execution_status"] == "completed"
    assert result["created_count"] == 2
    assert any(name == "show_output" for name, _ in events)
