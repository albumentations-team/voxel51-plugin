"""Read-only deletion scope for the selected run's confirmation screen."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Any

from albumentationsx_plugin.hosts.fiftyone.run_library import run_created_at
from albumentationsx_plugin.storage.manifest import FileRunStore, resolve_manifest_output_path


@dataclass(frozen=True, slots=True)
class CleanupPreview:
    run_key: str
    run_label: str
    created_at: str
    sample_count: int
    missing_sample_count: int
    file_count: int
    missing_file_count: int
    run_dir: str
    output_paths: tuple[str, ...]


def build_cleanup_preview(
    dataset: Any,
    run_key: str,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> CleanupPreview:
    """Count existing manifest-listed artifacts without modifying the dataset."""
    store = FileRunStore(dataset.name, storage_root=storage_root)
    manifest = store.load_manifest(run_key)
    if manifest.run_key != run_key:
        raise ValueError("Manifest run key does not match the selected run")
    run_dir = store.run_dir(run_key)
    paths = tuple(dict.fromkeys(manifest.output_paths))
    resolved = tuple(resolve_manifest_output_path(run_dir, path) for path in paths)
    if any(path.exists() and not path.is_file() for path in resolved):
        raise ValueError("A manifest output path is not a file. Repair the manifest before cleanup.")
    ids = tuple(dict.fromkeys(manifest.created_sample_ids))
    existing = len(dataset.select(list(ids)).values("id")) if ids else 0
    files = sum(path.is_file() for path in resolved)
    return CleanupPreview(
        run_key=run_key,
        run_label=str(manifest.metadata.get("run_label") or run_key),
        created_at=run_created_at(run_key, manifest.metadata),
        sample_count=existing,
        missing_sample_count=len(ids) - existing,
        file_count=files,
        missing_file_count=len(paths) - files,
        run_dir=str(run_dir),
        output_paths=paths,
    )
