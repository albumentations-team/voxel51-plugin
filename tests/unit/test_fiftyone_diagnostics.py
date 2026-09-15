from __future__ import annotations

from types import SimpleNamespace

import pytest

from albumentationsx_plugin.hosts.fiftyone.annotations import annotation_field_param_name
from albumentationsx_plugin.hosts.fiftyone.diagnostics import (
    DEBUG_BUNDLE_SCHEMA_VERSION,
    build_augmentation_debug_bundle,
)


@pytest.mark.unit
def test_build_augmentation_debug_bundle_includes_copyable_context() -> None:
    params = {
        "transform": "HorizontalFlip",
        "p": 1.0,
        annotation_field_param_name("ground_truth"): True,
        annotation_field_param_name("heatmap"): False,
        "_annotation_fields": {annotation_field_param_name("detections"): True},
        "non_json_value": object(),
    }
    errors = [
        {
            "code": "host_adapter_error",
            "message": "Selected annotation field cannot be transformed safely by the requested pipeline.",
            "context": {
                "reason": "annotation_target_incompatible",
                "field_name": "heatmap",
            },
        }
    ]
    ctx = SimpleNamespace(
        dataset=SimpleNamespace(name="demo-dataset", media_type="image"),
        view=SimpleNamespace(),
    )

    bundle = build_augmentation_debug_bundle(
        ctx=ctx,
        params=params,
        errors=errors,
        source_scope="selected_samples",
        pipeline_config={"transforms": [{"name": "HorizontalFlip", "params": {"p": 1.0}}]},
        selected_sample_ids=[f"sample-{index}" for index in range(25)],
        exception=RuntimeError("boom"),
        dry_run=False,
        preview_only=True,
    )

    assert bundle["schema_version"] == DEBUG_BUNDLE_SCHEMA_VERSION
    assert bundle["kind"] == "albumentationsx_augmentation_failure_debug_bundle"
    assert bundle["summary"] == errors[0]["message"]
    assert bundle["dataset"] == {
        "available": True,
        "name": "demo-dataset",
        "media_type": "image",
        "view_available": True,
        "view_type": "SimpleNamespace",
    }
    assert bundle["execution"] == {
        "source_scope": "selected_samples",
        "dry_run": False,
        "preview_only": True,
        "selected_sample_count": 25,
        "selected_sample_ids": [f"sample-{index}" for index in range(20)],
        "selected_sample_ids_truncated": True,
    }
    assert bundle["selected_annotation_fields"] == ["detections", "ground_truth"]
    assert bundle["exception"] == {"type": "RuntimeError", "message": "boom"}
    assert bundle["errors"] == errors
    assert bundle["pipeline_config"] == {"transforms": [{"name": "HorizontalFlip", "params": {"p": 1.0}}]}
    assert isinstance(bundle["operator_params"], dict)
    assert isinstance(bundle["operator_params"]["non_json_value"], str)
    dependency_versions = bundle["dependency_versions"]
    assert isinstance(dependency_versions, dict)
    assert set(dependency_versions) == {
        "plugin",
        "python",
        "fiftyone",
        "albumentationsx",
        "albu-spec",
    }
    assert str(bundle["capability_version_key"]).startswith("albumentationsx-")
    assert bundle["redaction_note"] == "This bundle does not include image data or file contents."
    assert bundle["suggested_next_steps"] == [
        "Check selected annotation fields and use a pipeline compatible with their target types."
    ]


@pytest.mark.unit
def test_build_augmentation_debug_bundle_handles_missing_context() -> None:
    bundle = build_augmentation_debug_bundle(
        ctx=None,
        params={},
        errors=[],
    )

    assert bundle["summary"] == "Augmentation failed without structured plugin errors."
    assert bundle["dataset"] == {
        "available": False,
        "name": "",
        "media_type": "",
        "view_available": False,
        "view_type": "",
    }
    execution = bundle["execution"]
    assert isinstance(execution, dict)
    assert execution["selected_sample_count"] == 0
    assert bundle["suggested_next_steps"] == [
        "Copy this debug bundle into the GitHub issue together with the visible traceback."
    ]
