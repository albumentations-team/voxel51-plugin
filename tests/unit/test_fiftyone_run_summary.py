from __future__ import annotations

import json
from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import (
    RUN_EXECUTION_CANCELLED_AT_METADATA_KEY,
    RUN_EXECUTION_STATUS_CANCELLED,
    RUN_EXECUTION_STATUS_COMPLETED,
    RUN_EXECUTION_STATUS_METADATA_KEY,
    PipelineConfig,
    RunManifest,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.run_summary import (
    RUN_OUTPUT_STATUS_AVAILABLE,
    RUN_OUTPUT_STATUS_CLEANED,
    RUN_OUTPUT_STATUS_MISSING_FILE,
    RUN_STATUS_CANCELLED,
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
    execution_status: str = RUN_EXECUTION_STATUS_COMPLETED,
    cancelled_at: str = "",
) -> RunManifest:
    metadata = {
        "output_dir": "/tmp/outputs",
        "output_tag": "albumentationsx-output",
        "fiftyone_run_key": build_fiftyone_run_key(run_key),
        RUN_EXECUTION_STATUS_METADATA_KEY: execution_status,
    }
    if run_label_slug:
        metadata["run_label"] = run_label
        metadata["run_label_slug"] = run_label_slug
    if cleanup_status:
        metadata["cleanup_status"] = cleanup_status
    if cleaned_at:
        metadata["cleaned_at"] = cleaned_at
    if cancelled_at:
        metadata[RUN_EXECUTION_CANCELLED_AT_METADATA_KEY] = cancelled_at

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
    dataset = _Dataset(sample_ids=("created-1",))
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
    assert summary.execution_status == RUN_EXECUTION_STATUS_COMPLETED
    assert summary.cancelled_at == ""
    assert summary.run_label == ""
    assert summary.run_label_slug == ""
    assert summary.pipeline_summary == "HorizontalFlip(p=1.0)"
    assert '"HorizontalFlip"' in summary.pipeline_config_json
    assert summary.generated_sample_ids == ("created-1",)
    assert summary.available_generated_sample_ids == ("created-1",)
    assert len(summary.generated_outputs) == 1
    output = summary.generated_outputs[0]
    assert output.status == RUN_OUTPUT_STATUS_AVAILABLE
    assert output.source_sample_id == "source-1"
    assert output.output_index == 0
    assert output.output_path == "images/output.png"
    assert output.generated_sample_id == "created-1"
    assert output.generated_sample_available is True
    assert output.output_file_available is True
    assert output.replay_available is True
    assert output.replay_record == {
        "source_sample_id": "source-1",
        "output_index": 0,
        "output_path": "images/output.png",
        "replay": {"applied": True},
    }
    assert summary.selected_output == output
    summary_json = summary.to_dict()
    assert json.loads(str(summary_json["generated_sample_ids_json"])) == ["created-1"]
    assert json.loads(str(summary_json["available_generated_sample_ids_json"])) == ["created-1"]
    assert json.loads(str(summary_json["selected_replay_json"]))["replay"] == {"applied": True}
    assert summary_json["execution_status"] == RUN_EXECUTION_STATUS_COMPLETED
    assert summary_json["cancelled_at"] == ""


@pytest.mark.unit
def test_build_run_summary_reports_cancelled_partial_run(tmp_path) -> None:
    dataset = _Dataset(sample_ids=("created-1",))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = _manifest(
        execution_status=RUN_EXECUTION_STATUS_CANCELLED,
        cancelled_at="2026-08-19T12:00:00Z",
    )
    store.save_manifest(manifest)
    output_path = store.run_dir(manifest.run_key) / "images/output.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake image bytes")

    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path)

    assert summary.status == RUN_STATUS_CANCELLED
    assert "cancelled" in summary.message
    assert summary.execution_status == RUN_EXECUTION_STATUS_CANCELLED
    assert summary.cancelled_at == "2026-08-19T12:00:00Z"
    assert summary.available_output_count == 1
    assert summary.generated_sample_ids == ("created-1",)


@pytest.mark.unit
def test_build_run_summary_selects_requested_output_replay(tmp_path) -> None:
    dataset = _Dataset(sample_ids=("created-1", "created-2"))
    store = FileRunStore(dataset.name, storage_root=tmp_path)
    manifest = RunManifest(
        run_key="albumentationsx-20260731T150000Z-summary",
        plugin_version="0.0.0",
        dependency_versions={"albumentationsx": "2.3.7", "albu-spec": "0.0.6", "fiftyone": "1.19.0"},
        pipeline=PipelineConfig(
            transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),),
            outputs_per_sample=2,
        ),
        source_sample_ids=("source-1",),
        created_sample_ids=("created-1", "created-2"),
        output_paths=("images/output-1.png", "images/output-2.png"),
        replay_records=(
            {
                "source_sample_id": "source-1",
                "output_index": 0,
                "output_path": "images/output-1.png",
                "replay": {"output": 1},
            },
            {
                "source_sample_id": "source-1",
                "output_index": 1,
                "output_path": "images/output-2.png",
                "replay": {"output": 2},
            },
        ),
        counters={"processed": 1, "created": 2, "skipped": 0, "errors": 0, "outputs": 2},
        metadata={
            "output_dir": "/tmp/outputs",
            "output_tag": "albumentationsx-output",
            "fiftyone_run_key": build_fiftyone_run_key("albumentationsx-20260731T150000Z-summary"),
        },
    )
    store.save_manifest(manifest)
    for relative_path in manifest.output_paths:
        output_path = store.run_dir(manifest.run_key) / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake image bytes")

    requested_key = "1|source-1|1|images/output-2.png"
    summary = build_run_summary(dataset, manifest.run_key, storage_root=tmp_path, selected_output_key=requested_key)

    assert summary.selected_output_key == requested_key
    assert summary.selected_output is not None
    assert summary.selected_output.output_index == 1
    assert summary.selected_output.replay_record == {
        "source_sample_id": "source-1",
        "output_index": 1,
        "output_path": "images/output-2.png",
        "replay": {"output": 2},
    }
    assert json.loads(str(summary.to_dict()["selected_replay_json"]))["replay"] == {"output": 2}


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
    assert summary.generated_outputs[0].status == RUN_OUTPUT_STATUS_CLEANED
    assert summary.generated_outputs[0].replay_available is True
    assert json.loads(str(summary.to_dict()["selected_replay_json"]))["replay"] == {"applied": True}


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
    assert summary.generated_outputs[0].status == RUN_OUTPUT_STATUS_MISSING_FILE
    assert summary.generated_outputs[0].output_file_available is False


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
