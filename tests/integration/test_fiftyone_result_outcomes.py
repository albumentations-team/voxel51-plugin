from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.core import InvalidParameterError
from albumentationsx_plugin.hosts.fiftyone.augmentation import executor, preview
from albumentationsx_plugin.hosts.fiftyone.editor_draft import EDITOR_ACTION, RESULT_DETAILS
from albumentationsx_plugin.hosts.fiftyone.operators.augment import AugmentWithAlbumentationsX
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import ViewAlbumentationsXRun
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import cleanup_run
from albumentationsx_plugin.hosts.fiftyone.run_summary import build_run_summary
from albumentationsx_plugin.storage import FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = pytest.mark.integration


@pytest.fixture
def result_context(tmp_path):
    path = write_rgb_image(np.arange(240, dtype=np.uint8).reshape(8, 10, 3), tmp_path, "source.png")
    dataset = fo.Dataset(f"vox74-results-{uuid4().hex}")
    try:
        ids = dataset.add_samples([fo.Sample(filepath=str(path), tags=["source"]) for _ in range(3)])
        ctx = SimpleNamespace(dataset=dataset, view=dataset, selected=ids, params={})
        ctx.params = {"transform": "HorizontalFlip", "p": 1.0, "_storage_root": str(tmp_path / "runs")}
        yield ctx, path
    finally:
        dataset.delete()


def _fields(schema):
    result = {}
    for name, prop in schema["type"]["properties"].items():
        result[name] = prop
        if prop["type"]["name"] == "Object":
            result.update(_fields(prop))
    return result


def _assert_clean_report(ctx, result):
    op = AugmentWithAlbumentationsX()
    ctx.results = result
    schema = op.resolve_output(ctx).to_json()
    fields = _fields(schema)
    assert next(iter(schema["type"]["properties"])) == "_outcome"
    assert "errors" not in fields  # No editable list or empty-list invitation.
    assert result["execution_status"]
    for name, prop in fields.items():
        if prop["type"]["name"] == "Object" or name.startswith("_") or name == "preview_display_policy":
            continue
        assert name in result and result[name] not in (None, "", "[]", "{}")
    return fields


@pytest.mark.parametrize(
    "action,count,status",
    [
        ("preview", 1, "preview"),
        ("preview", 3, "preview"),
        ("validate", 1, "dry_run"),
        ("save", 1, "preset_saved"),
        ("create", 1, "completed"),
    ],
)
def test_successful_action_reports_are_conditional_and_read_only(result_context, action, count, status):
    ctx, path = result_context
    before = path.read_bytes()
    ctx.selected = ctx.selected[:count]
    ctx.params.update({EDITOR_ACTION: action, "save_preset_name": "Result pipeline"})
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["execution_status"] == status
    fields = _assert_clean_report(ctx, result)
    assert not any(name.startswith("_error_") for name in fields)
    assert ("_open_generated_samples" in fields) == (action == "create")
    assert ("preset_name" in fields) == (action == "save")
    for slot in range(1, 4):
        assert (f"preview_{slot}_comparison_image" in fields) == (action == "preview" and slot <= count)
    if action in {"preview", "validate"}:
        assert "run_key" not in fields and "output_dir" not in fields
    if action == "preview":
        assert "No samples" in result["preview_note"]
        assert fields["preview_1_replay_json"]["view"]["name"] == "JSONView"
        assert fields["_download_preview_1_replay_json"]["view"]["href"].startswith("data:application/json;base64,")
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["no_selection", "crop", "annotation"])
def test_validation_failures_show_cause_and_recovery_before_details(result_context, failure):
    ctx, _path = result_context
    ctx.params[EDITOR_ACTION] = "preview"
    if failure == "no_selection":
        ctx.selected = []
    elif failure == "crop":
        ctx.params.update(transform="RandomCrop", height=9999, width=9999)
    else:
        sample = ctx.dataset.first()
        sample["joints"] = fo.Keypoints(keypoints=[fo.Keypoint(points=[(float("inf"), 0.5)])])
        sample.save()
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["execution_status"] == "failed" and result["created_count"] == 0
    fields = _assert_clean_report(ctx, result)
    assert "Next:" in fields["_error_1"]["view"]["description"]
    assert "_back_to_editor" in fields and "_open_generated_samples" not in fields
    bundle = json.loads(result["debug_bundle_json"])
    assert bundle["execution"]["execution_status"] == "failed"
    assert not ctx.dataset.list_runs()


@pytest.mark.parametrize("mode", ["failed", "partial", "cancelled"])
@pytest.mark.parametrize("delegated", [False, True])
def test_runtime_outcomes_agree_across_result_manifest_history_and_cleanup(
    result_context, monkeypatch, mode, delegated
):
    ctx, path = result_context
    before = path.read_bytes()
    ctx.delegated = delegated
    ctx.params[EDITOR_ACTION] = "create"
    original = executor._prepare_one_output
    calls = 0

    def fail_after_preflight(**kwargs):
        nonlocal calls
        calls += 1
        if mode == "failed" or calls > 1:
            raise InvalidParameterError(
                "RandomCrop", "height", "Sampled crop exceeds image height", {"stage_number": 1}
            )
        return original(**kwargs)

    if mode == "cancelled":
        ctx.is_cancelled = lambda: len(ctx.dataset) > 3
    monkeypatch.setattr(executor, "_prepare_one_output", fail_after_preflight)
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["execution_status"] == mode
    store = FileRunStore(ctx.dataset.name, storage_root=ctx.params["_storage_root"])
    manifest = store.load_manifest(result["run_key"])
    assert manifest.metadata["execution_status"] == mode
    custom = ctx.dataset.load_run_results(result["fiftyone_run_key"])
    assert custom.manifest["metadata"]["execution_status"] == mode
    summary = build_run_summary(ctx.dataset, result["run_key"], storage_root=ctx.params["_storage_root"])
    assert summary.execution_status == mode
    assert summary.skipped_count == result["skipped_count"]
    fields = _assert_clean_report(ctx, result)
    assert ("_open_generated_samples" in fields) == (mode != "failed")
    assert json.loads(result["debug_bundle_json"])["execution"]["execution_status"] == mode
    if mode != "cancelled":
        assert "Sample:" in fields["_error_1"]["view"]["description"]
        assert "Stage: 1" in fields["_error_1"]["view"]["description"]
        # Legacy incorrectly completed manifests get a truthful read-only summary.
        store.save_manifest(replace(manifest, metadata={**manifest.metadata, "execution_status": "completed"}))
        assert (
            build_run_summary(ctx.dataset, result["run_key"], storage_root=ctx.params["_storage_root"]).execution_status
            == mode
        )
    cleanup_run(ctx.dataset, result["run_key"], storage_root=ctx.params["_storage_root"], confirmed=True)
    assert len(ctx.dataset) == 3 and path.read_bytes() == before


def test_output_navigation_replaces_source_filters_and_keeps_run_identity(result_context):
    ctx, _path = result_context
    ctx.params[EDITOR_ACTION] = "create"
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    fields = _assert_clean_report(ctx, result)
    button = fields["_open_generated_samples"]["view"]
    assert button["operator"] == "@albumentations/albumentationsx/view_albumentationsx_run"
    events = []
    ctx.trigger = lambda name, params=None: events.append((name, params))
    ctx.view = ctx.dataset.match_tags("source")
    ctx.params = button["params"]
    report = ViewAlbumentationsXRun().execute(ctx)
    event, params = events[-1]
    assert event == "set_view"
    assert params is not None
    assert len(params["view"]) == 1
    stage = params["view"][0]
    assert stage["_cls"] == "fiftyone.core.stages.Select"
    assert dict(stage["kwargs"])["sample_ids"] == json.loads(str(report["available_generated_sample_ids_json"]))
    ctx.results = report
    report_fields = _fields(ViewAlbumentationsXRun().resolve_output(ctx).to_json())
    assert "_outcome" in report_fields and RESULT_DETAILS in report_fields


@pytest.mark.parametrize("succeeded", [0, 1])
def test_preview_runtime_failures_have_failed_or_partial_status(result_context, monkeypatch, succeeded):
    ctx, _path = result_context
    ctx.params[EDITOR_ACTION] = "preview"
    original = preview.apply_output
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls > succeeded:
            raise InvalidParameterError("RandomCrop", "height", "Sampled crop exceeds image height")
        return original(**kwargs)

    monkeypatch.setattr(preview, "apply_output", fail)
    result = cast(dict[str, Any], AugmentWithAlbumentationsX().execute(ctx))
    assert result["execution_status"] == ("partial" if succeeded else "failed")
    fields = _assert_clean_report(ctx, result)
    assert ("preview_1_comparison_image" in fields) == bool(succeeded)
    assert not ctx.dataset.list_runs()
