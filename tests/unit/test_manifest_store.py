from __future__ import annotations

from pathlib import Path

import pytest

from albumentationsx_plugin.core import MediaIOError, PipelineConfig, RunManifest, TransformConfig
from albumentationsx_plugin.storage import MANIFEST_FILENAME, FileRunStore, resolve_manifest_output_path


def _manifest(
    *,
    run_key: str = "albumentationsx-20260731T150000Z-vox15",
    output_paths: tuple[str, ...] = ("images/output.png",),
) -> RunManifest:
    return RunManifest(
        run_key=run_key,
        plugin_version="0.0.0",
        dependency_versions={"albumentationsx": "2.3.7", "albu-spec": "0.0.6", "fiftyone": "1.19.0"},
        pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),)),
        source_sample_ids=("source-1",),
        created_sample_ids=("created-1",),
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
    )


@pytest.mark.unit
def test_file_run_store_round_trips_manifest_with_atomic_replace(tmp_path) -> None:
    store = FileRunStore(dataset_name="dataset with / odd chars", storage_root=tmp_path)
    manifest = _manifest()

    store.save_manifest(manifest)
    loaded = store.load_manifest(manifest.run_key)

    assert loaded == manifest
    assert store.list_run_keys() == (manifest.run_key,)
    assert store.manifest_path(manifest.run_key) == store.run_dir(manifest.run_key) / MANIFEST_FILENAME
    assert store.manifest_path(manifest.run_key).parent.parent.parent == tmp_path
    assert store.manifest_path(manifest.run_key).parent.name == manifest.run_key
    assert store.manifest_path(manifest.run_key).parent.parent.name.startswith("dataset-with-odd-chars-")

    updated = RunManifest.from_dict(
        {
            **manifest.to_dict(),
            "created_sample_ids": ["created-1", "created-2"],
            "output_paths": ["images/output.png", "images/output-2.png"],
            "counters": {"processed": 1, "created": 2, "skipped": 0, "errors": 0, "outputs": 2},
        }
    )
    store.save_manifest(updated)

    assert store.load_manifest(manifest.run_key) == updated
    assert list(store.run_dir(manifest.run_key).glob(".manifest.*.tmp")) == []


@pytest.mark.unit
def test_file_run_store_rejects_unsafe_manifest_paths(tmp_path) -> None:
    store = FileRunStore(dataset_name="dataset", storage_root=tmp_path)

    with pytest.raises(MediaIOError) as traversal_error:
        store.save_manifest(_manifest(output_paths=("../outside.png",)))

    with pytest.raises(MediaIOError) as absolute_error:
        store.save_manifest(_manifest(output_paths=(str(tmp_path / "outside.png"),)))

    assert traversal_error.value.context["reason"] == "unsafe_manifest_output_path"
    assert absolute_error.value.context["reason"] == "absolute_manifest_output_path"


@pytest.mark.unit
def test_resolve_manifest_output_path_proves_run_dir_containment(tmp_path) -> None:
    run_dir = tmp_path / "dataset" / "run"

    resolved = resolve_manifest_output_path(run_dir, "images/output.png")

    assert resolved == (run_dir / "images/output.png").resolve()

    with pytest.raises(MediaIOError) as error:
        resolve_manifest_output_path(run_dir, Path("images") / ".." / ".." / "outside.png")

    assert error.value.context["reason"] == "unsafe_manifest_output_path"


@pytest.mark.unit
def test_file_run_store_reports_missing_and_invalid_manifest_files(tmp_path) -> None:
    store = FileRunStore(dataset_name="dataset", storage_root=tmp_path)
    run_key = "albumentationsx-20260731T150000Z-missing"

    with pytest.raises(MediaIOError) as missing_error:
        store.load_manifest(run_key)

    store.run_dir(run_key).mkdir(parents=True)
    store.manifest_path(run_key).write_text("[]", encoding="utf-8")

    with pytest.raises(MediaIOError) as invalid_error:
        store.load_manifest(run_key)

    assert missing_error.value.context["reason"] == "missing_manifest"
    assert invalid_error.value.context["reason"] == "invalid_manifest_shape"

    store.delete_manifest(run_key)

    assert not store.manifest_path(run_key).exists()
