from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import PipelineConfig, RunManifest, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import (
    CLEANUP_STATUS_CLEANED,
    CLEANUP_STATUS_CONFIRMATION_REQUIRED,
    CLEANUP_STATUS_INVALID,
    CLEANUP_STATUS_OK,
    CLEANUP_STATUS_PARTIAL,
    cleanup_run,
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
    name = "run-cleanup-dataset"

    def __init__(
        self,
        *,
        sample_ids: tuple[str, ...] = (),
        plugin_run_keys: tuple[str, ...] = (),
    ) -> None:
        self.sample_ids = set(sample_ids)
        self.deleted_sample_ids: list[str] = []
        self.run_keys = {build_fiftyone_run_key(run_key) for run_key in plugin_run_keys}
        self.deleted_run_keys: list[str] = []

    def list_runs(self) -> list[str]:
        return sorted(self.run_keys)

    def has_run(self, run_key: str) -> bool:
        return run_key in self.run_keys

    def delete_run(self, run_key: str) -> None:
        self.run_keys.remove(run_key)
        self.deleted_run_keys.append(run_key)

    def select(self, sample_ids: Sequence[str], ordered: bool = False) -> _View:
        assert ordered is False
        return _View(self.sample_ids.intersection(sample_ids))

    def delete_samples(self, samples_or_ids: Sequence[str]) -> None:
        for sample_id in samples_or_ids:
            self.sample_ids.remove(sample_id)
            self.deleted_sample_ids.append(sample_id)

    def get_run_info(self, run_key: str) -> SimpleNamespace:
        return SimpleNamespace(config=SimpleNamespace(method=FIFTYONE_RUN_METHOD, plugin_run_key=run_key))


def _manifest(
    *,
    run_key: str = "albumentationsx-20260731T150000Z-cleanup",
    created_sample_ids: tuple[str, ...] = ("created-1",),
    output_paths: tuple[str, ...] = ("images/output.png",),
) -> RunManifest:
    return RunManifest(
        run_key=run_key,
        plugin_version="0.0.0",
        dependency_versions={"albumentationsx": "2.3.7", "albu-spec": "0.0.6", "fiftyone": "1.19.0"},
        pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),)),
        source_sample_ids=("source-1",),
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=(),
        counters={"processed": 1, "created": len(created_sample_ids), "skipped": 0, "errors": 0, "outputs": 1},
        metadata={
            "output_dir": "/tmp/outputs",
            "output_tag": "albumentationsx-output",
            "fiftyone_run_key": build_fiftyone_run_key(run_key),
        },
    )


@pytest.mark.unit
def test_cleanup_run_requires_confirmation_before_mutating(tmp_path) -> None:
    dataset = _Dataset(sample_ids=("source-1", "created-1"))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest()
    store.save_manifest(manifest)
    output_path = _write_output(store, manifest.run_key, "images/output.png")

    result = cleanup_run(dataset, manifest.run_key, confirmed=False, storage_root=tmp_path)

    assert result.status == CLEANUP_STATUS_CONFIRMATION_REQUIRED
    assert result.confirmed is False
    assert dataset.sample_ids == {"source-1", "created-1"}
    assert output_path.exists()
    assert store.manifest_path(manifest.run_key).exists()


@pytest.mark.unit
def test_cleanup_run_deletes_generated_samples_files_and_custom_run_idempotently(tmp_path) -> None:
    manifest = _manifest()
    dataset = _Dataset(sample_ids=("source-1", "created-1"), plugin_run_keys=(manifest.run_key,))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    store.save_manifest(manifest)
    output_path = _write_output(store, manifest.run_key, "images/output.png")

    result = cleanup_run(dataset, manifest.run_key, confirmed=True, storage_root=tmp_path)

    assert result.status == CLEANUP_STATUS_OK
    assert result.deleted_sample_count == 1
    assert result.skipped_sample_count == 0
    assert result.deleted_file_count == 1
    assert result.skipped_file_count == 0
    assert result.custom_run_deleted is True
    assert result.custom_run_missing is False
    assert dataset.sample_ids == {"source-1"}
    assert dataset.deleted_sample_ids == ["created-1"]
    assert dataset.deleted_run_keys == [build_fiftyone_run_key(manifest.run_key)]
    assert not output_path.exists()
    assert store.manifest_path(manifest.run_key).exists()
    cleaned_manifest = store.load_manifest(manifest.run_key)
    assert cleaned_manifest.metadata["cleanup_status"] == "cleaned"
    assert isinstance(cleaned_manifest.metadata["cleaned_at"], str)

    repeated = cleanup_run(dataset, manifest.run_key, confirmed=True, storage_root=tmp_path)

    assert repeated.status == CLEANUP_STATUS_CLEANED
    assert repeated.message == "Run was already cleaned; nothing remained to delete."
    assert repeated.deleted_sample_count == 0
    assert repeated.skipped_sample_count == 1
    assert repeated.deleted_file_count == 0
    assert repeated.skipped_file_count == 1
    assert repeated.custom_run_deleted is False
    assert repeated.custom_run_missing is True
    assert dataset.sample_ids == {"source-1"}


@pytest.mark.unit
def test_cleanup_run_rejects_unsafe_manifest_paths_before_mutating(tmp_path) -> None:
    manifest = _manifest(output_paths=("../outside.png",))
    dataset = _Dataset(sample_ids=("source-1", "created-1"), plugin_run_keys=(manifest.run_key,))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    store.run_dir(manifest.run_key).mkdir(parents=True)
    store.manifest_path(manifest.run_key).write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"do not delete")

    result = cleanup_run(dataset, manifest.run_key, confirmed=True, storage_root=tmp_path)

    assert result.status == CLEANUP_STATUS_INVALID
    assert dataset.sample_ids == {"source-1", "created-1"}
    assert outside_path.exists()
    assert dataset.has_run(build_fiftyone_run_key(manifest.run_key))


@pytest.mark.unit
def test_cleanup_run_reports_malformed_manifest_without_mutating(tmp_path) -> None:
    run_key = "albumentationsx-20260731T150000Z-malformed"
    dataset = _Dataset(sample_ids=("created-1",), plugin_run_keys=(run_key,))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    store.run_dir(run_key).mkdir(parents=True)
    store.manifest_path(run_key).write_text("[]", encoding="utf-8")

    result = cleanup_run(dataset, run_key, confirmed=True, storage_root=tmp_path)

    assert result.status == CLEANUP_STATUS_INVALID
    assert dataset.sample_ids == {"created-1"}
    assert dataset.has_run(build_fiftyone_run_key(run_key))


@pytest.mark.unit
def test_cleanup_run_reports_mixed_success_without_deleting_custom_run(tmp_path) -> None:
    manifest = _manifest(output_paths=("images/output.png", "images/not-a-file"))
    dataset = _Dataset(sample_ids=("created-1",), plugin_run_keys=(manifest.run_key,))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    store.save_manifest(manifest)
    output_path = _write_output(store, manifest.run_key, "images/output.png")
    directory_path = store.run_dir(manifest.run_key) / "images/not-a-file"
    directory_path.mkdir()

    result = cleanup_run(dataset, manifest.run_key, confirmed=True, storage_root=tmp_path)

    assert result.status == CLEANUP_STATUS_PARTIAL
    assert result.deleted_sample_count == 1
    assert result.deleted_file_count == 1
    assert result.failed_file_count == 1
    assert result.custom_run_deleted is False
    assert result.custom_run_missing is False
    errors_json = result.to_dict()["errors_json"]
    assert isinstance(errors_json, str)
    assert '"not_a_file"' in errors_json
    assert not output_path.exists()
    assert directory_path.exists()
    assert dataset.has_run(build_fiftyone_run_key(manifest.run_key))


def _write_output(store: FileRunStore, run_key: str, relative_path: str) -> Path:
    output_path = store.run_dir(run_key) / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake image bytes")
    return output_path
