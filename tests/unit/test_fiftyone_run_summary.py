from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import PipelineConfig, RunManifest, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.run_summary import (
    RUN_STATUS_CLEANED,
    RUN_STATUS_INVALID,
    RUN_STATUS_MISSING,
    RUN_STATUS_OK,
    RUN_STATUS_STALE,
    build_run_summary,
    list_available_run_keys,
    list_deletable_run_keys,
)
from albumentationsx_plugin.hosts.fiftyone.runs import FIFTYONE_RUN_METHOD, build_fiftyone_run_key
from albumentationsx_plugin.storage import FileRunStore


class _View:
    def __init__(self, sample_ids: set[str]) -> None:
        self._sample_ids = sample_ids

    def values(self, field_or_expr: str) -> list[str]:
        assert field_or_expr == "id"
        return sorted(self._sample_ids)


class _Dataset:
    name = "run-summary-dataset"

    def __init__(self, plugin_run_keys: tuple[str, ...] = (), sample_ids: tuple[str, ...] = ()) -> None:
        self._plugin_run_keys = plugin_run_keys
        self._sample_ids = set(sample_ids)

    def list_runs(self) -> list[str]:
        return [build_fiftyone_run_key(run_key) for run_key in self._plugin_run_keys]

    def has_run(self, run_key: str) -> bool:
        return run_key in self.list_runs()

    def get_run_info(self, run_key: str) -> SimpleNamespace:
        for plugin_run_key in self._plugin_run_keys:
            if build_fiftyone_run_key(plugin_run_key) == run_key:
                return SimpleNamespace(
                    config=SimpleNamespace(method=FIFTYONE_RUN_METHOD, plugin_run_key=plugin_run_key)
                )
        return SimpleNamespace(config=SimpleNamespace(method="other"))

    def select(self, sample_ids: Sequence[str], ordered: bool = False) -> _View:
        assert ordered is False
        return _View(self._sample_ids.intersection(sample_ids))


def _manifest(
    *,
    run_key: str = "albumentationsx-20260731T150000Z-summary",
    created_sample_ids: tuple[str, ...] = ("created-1",),
    output_paths: tuple[str, ...] = ("images/output.png",),
    run_label: str = "",
    run_label_slug: str = "",
    cleanup_status: str = "",
    cleaned_at: str = "",
) -> RunManifest:
    metadata = {
        "output_dir": "/tmp/outputs",
        "output_tag": "albumentationsx-output",
        "fiftyone_run_key": build_fiftyone_run_key(run_key),
    }
    if run_label_slug:
        metadata["run_label"] = run_label
        metadata["run_label_slug"] = run_label_slug
    if cleanup_status:
        metadata["cleanup_status"] = cleanup_status
    if cleaned_at:
        metadata["cleaned_at"] = cleaned_at

    return RunManifest(
        run_key=run_key,
        plugin_version="0.0.0",
        dependency_versions={"albumentationsx": "2.3.7", "albu-spec": "0.0.6", "fiftyone": "1.19.0"},
        pipeline=PipelineConfig(
            transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),),
            outputs_per_sample=1,
        ),
        source_sample_ids=("source-1",),
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=(
            {
                "source_sample_id": "source-1",
                "output_index": 0,
                "output_path": "images/output.png",
                "replay": {"applied": True},
            },
        ),
        counters={"processed": 1, "created": 1, "skipped": 0, "errors": 0, "outputs": len(output_paths)},
        metadata=metadata,
    )


@pytest.mark.unit
def test_build_run_summary_reads_values_from_manifest(tmp_path) -> None:
    dataset = _Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest()
    store.save_manifest(manifest)
    output_path = store.run_dir(manifest.run_key) / "images/output.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake image bytes")

    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_OK
    assert summary.message == "Run manifest loaded."
    assert summary.source_count == 1
    assert summary.created_count == 1
    assert summary.output_count == 1
    assert summary.available_output_count == 1
    assert summary.missing_output_count == 0
    assert summary.error_count == 0
    assert summary.replay_count == 1
    assert summary.replay_available is True
    assert summary.output_tag == "albumentationsx-output"
    assert summary.cleanup_status == ""
    assert summary.cleaned_at == ""
    assert summary.run_label == ""
    assert summary.run_label_slug == ""
    assert summary.pipeline_summary == "HorizontalFlip(p=1.0)"
    assert '"HorizontalFlip"' in summary.pipeline_config_json


@pytest.mark.unit
def test_build_run_summary_exposes_run_label_metadata(tmp_path) -> None:
    dataset = _Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest(
        run_key="cats-crop-test-albumentationsx-20260731T150000Z-summary",
        run_label="Cats crop test",
        run_label_slug="cats-crop-test",
    )
    store.save_manifest(manifest)

    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path)

    assert summary.run_label == "Cats crop test"
    assert summary.run_label_slug == "cats-crop-test"
    assert summary.to_dict()["run_label"] == "Cats crop test"
    assert summary.to_dict()["run_label_slug"] == "cats-crop-test"


@pytest.mark.unit
def test_build_run_summary_reports_cleaned_manifest(tmp_path) -> None:
    dataset = _Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest(cleanup_status="cleaned", cleaned_at="2026-07-31T15:00:00Z")
    store.save_manifest(manifest)

    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_CLEANED
    assert summary.message == "Run has been cleaned; manifest is retained for audit."
    assert summary.cleanup_status == "cleaned"
    assert summary.cleaned_at == "2026-07-31T15:00:00Z"
    assert summary.to_dict()["cleanup_status"] == "cleaned"
    assert summary.to_dict()["cleaned_at"] == "2026-07-31T15:00:00Z"


@pytest.mark.unit
def test_build_run_summary_reports_stale_missing_outputs(tmp_path) -> None:
    dataset = _Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest()
    store.save_manifest(manifest)

    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_STALE
    assert summary.available_output_count == 0
    assert summary.missing_output_count == 1
    assert "output file(s) are missing" in summary.message


@pytest.mark.unit
def test_list_deletable_run_keys_filters_cleaned_manifest_only_runs(tmp_path) -> None:
    dataset = _Dataset(
        plugin_run_keys=("albumentationsx-20260731T150000Z-custom",),
        sample_ids=("created-sample",),
    )
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    has_sample = _manifest(
        run_key="albumentationsx-20260731T150000Z-has-sample",
        created_sample_ids=("created-sample",),
        output_paths=(),
    )
    has_output = _manifest(
        run_key="albumentationsx-20260731T150000Z-has-output",
        created_sample_ids=(),
        output_paths=("images/output.png",),
    )
    cleaned = _manifest(
        run_key="albumentationsx-20260731T150000Z-cleaned",
        created_sample_ids=("created-missing",),
        output_paths=("images/missing.png",),
        cleanup_status="cleaned",
        cleaned_at="2026-07-31T15:00:00Z",
    )
    invalid_run_key = "albumentationsx-20260731T150000Z-invalid"
    store.save_manifest(has_sample)
    store.save_manifest(has_output)
    store.save_manifest(cleaned)
    output_path = store.run_dir(has_output.run_key) / "images/output.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake image bytes")
    store.run_dir(invalid_run_key).mkdir(parents=True)
    store.manifest_path(invalid_run_key).write_text("[]", encoding="utf-8")

    assert list_deletable_run_keys(dataset, storage_root=tmp_path) == (
        "albumentationsx-20260731T150000Z-custom",
        "albumentationsx-20260731T150000Z-has-output",
        "albumentationsx-20260731T150000Z-has-sample",
    )
    assert list_available_run_keys(dataset, storage_root=tmp_path) == (
        "albumentationsx-20260731T150000Z-cleaned",
        "albumentationsx-20260731T150000Z-custom",
        "albumentationsx-20260731T150000Z-has-output",
        "albumentationsx-20260731T150000Z-has-sample",
        "albumentationsx-20260731T150000Z-invalid",
    )


@pytest.mark.unit
def test_build_run_summary_reports_missing_manifest_for_custom_run(tmp_path) -> None:
    run_key = "albumentationsx-20260731T150000Z-missing"
    dataset = _Dataset(plugin_run_keys=(run_key,))

    summary = build_run_summary(dataset, run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_MISSING
    assert summary.fiftyone_run_key == build_fiftyone_run_key(run_key)
    assert summary.manifest_path == str(FileRunStore(dataset.name, storage_root=tmp_path).manifest_path(run_key))
    assert "custom run exists" in summary.message


@pytest.mark.unit
def test_build_run_summary_reports_invalid_manifest_without_crashing(tmp_path) -> None:
    dataset = _Dataset()
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    run_key = "albumentationsx-20260731T150000Z-invalid"
    store.run_dir(run_key).mkdir(parents=True)
    store.manifest_path(run_key).write_text("[]", encoding="utf-8")

    summary = build_run_summary(dataset, run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_INVALID
    assert summary.run_key == run_key
    assert summary.manifest_path == str(store.manifest_path(run_key))
    assert summary.message


@pytest.mark.unit
def test_list_available_run_keys_unions_valid_invalid_and_custom_runs(tmp_path) -> None:
    dataset = _Dataset(plugin_run_keys=("albumentationsx-20260731T150000Z-custom",))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    valid_manifest = _manifest(run_key="albumentationsx-20260731T150000Z-valid")
    invalid_run_key = "albumentationsx-20260731T150000Z-invalid"
    store.save_manifest(valid_manifest)
    store.run_dir(invalid_run_key).mkdir(parents=True)
    store.manifest_path(invalid_run_key).write_text("[]", encoding="utf-8")

    assert list_available_run_keys(dataset, storage_root=tmp_path) == (
        "albumentationsx-20260731T150000Z-custom",
        "albumentationsx-20260731T150000Z-invalid",
        "albumentationsx-20260731T150000Z-valid",
    )
