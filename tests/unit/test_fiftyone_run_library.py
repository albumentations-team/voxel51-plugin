from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import PipelineConfig, RunManifest, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.run_library import classify_run, list_run_library, run_created_at
from albumentationsx_plugin.hosts.fiftyone.runs import FIFTYONE_RUN_METHOD
from albumentationsx_plugin.storage import FileRunStore


class Dataset:
    name = "run-library-tests"

    def list_runs(self):
        return ["missing", "broken", "unrelated", "completed"]

    def get_run_info(self, run_key: str):
        key = run_key
        if key == "broken":
            raise ValueError("Stale custom run")
        return SimpleNamespace(
            config=SimpleNamespace(
                method="other" if key == "unrelated" else FIFTYONE_RUN_METHOD,
                plugin_run_key=key,
                run_label="Missing run" if key == "missing" else "",
            )
        )

    def select(self, *args, **kwargs):
        raise AssertionError("Library listing must not query generated samples")


def manifest(**kwargs):
    return RunManifest(
        run_key="completed",
        plugin_version="0.1.0",
        dependency_versions={"albu-spec": "0.0.6", "albumentationsx": "2.3.8"},
        pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),)),
        **kwargs,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("metadata", "outputs", "errors", "expected"),
    [
        ({}, 1, 0, "completed"),
        ({}, 0, 1, "failed"),
        ({}, 1, 1, "partial"),
        ({"execution_status": "cancelled"}, 1, 1, "cancelled"),
        ({"execution_status": "running"}, 1, 1, "running"),
        ({"execution_status": "failed"}, 0, 0, "failed"),
        ({"execution_status": "partial"}, 1, 0, "partial"),
        ({"cleanup_status": "cleaned", "execution_status": "cancelled"}, 1, 1, "cleaned"),
        ({"execution_status": []}, 0, 0, "completed"),
    ],
)
def test_classification_preserves_cleanup_and_cancellation(metadata, outputs, errors, expected):
    assert classify_run(manifest(metadata=metadata, counters={"outputs": outputs, "errors": errors})) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "metadata", "expected"),
    [
        ("cats-albumentationsx-20260909T120000Z-abc", {}, "2026-09-09T12:00:00+00:00"),
        ("legacy", {"created_at": "2026-09-09T15:00:00+03:00"}, "2026-09-09T12:00:00+00:00"),
        ("legacy", {}, ""),
        ("albumentationsx-20269999T120000Z-abc", {"created_at": "invalid"}, ""),
    ],
)
def test_creation_date_supports_legacy_keys_and_normalizes_timezones(key, metadata, expected):
    assert run_created_at(key, metadata) == expected


@pytest.mark.unit
def test_library_merges_sorts_and_tolerates_invalid_records(tmp_path):
    dataset = Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    completed = manifest(
        source_sample_ids=("source-1", "source-2"),
        counters={"processed": 1, "outputs": 3, "errors": 1},
        metadata={"run_label": "Cats", "created_at": "2026-09-08T20:00:00Z", "execution_scope": "current_view"},
    )
    store.save_manifest(completed)
    store.save_manifest(
        replace(
            completed,
            run_key="cleaned",
            metadata={
                "run_label": "Cats",
                "created_at": "2026-09-09T12:00:00Z",
                "cleanup_status": "cleaned",
            },
        )
    )
    corrupt = store.manifest_path("invalid")
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not json")
    entries = list_run_library(dataset, storage_root=tmp_path)
    assert [entry.run_key for entry in entries] == ["cleaned", "completed", "missing", "invalid"]
    clean, partial, missing, invalid = entries
    assert clean.status == "cleaned"
    assert clean.manifest_available
    assert partial.display_name == "Cats"
    assert partial.status == "partial"
    assert partial.source_count == 2
    assert partial.output_count == 3
    assert partial.execution_scope == "current_view"
    assert "HorizontalFlip" in partial.pipeline_summary
    assert "albu-spec 0.0.6" in partial.dependency_summary
    assert partial.choice_label != clean.choice_label
    assert missing.display_name == "Missing run"
    assert missing.status == "missing_manifest"
    assert invalid.status == "invalid_manifest"
    assert not missing.manifest_available
    assert not invalid.manifest_available
    assert corrupt.read_text() == "not json"
    assert store.load_manifest("completed") == completed
