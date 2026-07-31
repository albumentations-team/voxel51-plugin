"""Read-only summaries for persisted AlbumentationsX FiftyOne runs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Protocol

from albumentationsx_plugin.core import JSONDict, MediaIOError, RunManifest
from albumentationsx_plugin.hosts.fiftyone.runs import FIFTYONE_RUN_METHOD, build_fiftyone_run_key
from albumentationsx_plugin.hosts.fiftyone.samples import summarize_pipeline
from albumentationsx_plugin.storage.manifest import (
    MANIFEST_FILENAME,
    FileRunStore,
    resolve_manifest_output_path,
)

RUN_STATUS_OK = "ok"
RUN_STATUS_STALE = "stale"
RUN_STATUS_MISSING = "missing_manifest"
RUN_STATUS_INVALID = "invalid_manifest"
RUN_STATUS_NOT_FOUND = "not_found"
RUN_STATUS_INPUT_REQUIRED = "input_required"


class RunDataset(Protocol):
    """Read-only subset of FiftyOne dataset APIs needed for run summaries."""

    name: str

    def list_runs(self) -> Sequence[str]:
        """Return registered FiftyOne run keys."""
        ...

    def has_run(self, run_key: str) -> bool:
        """Return whether a FiftyOne run exists."""
        ...

    def get_run_info(self, run_key: str) -> Any:
        """Return FiftyOne run metadata."""
        ...


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Read-only summary of a persisted AlbumentationsX run."""

    run_key: str
    status: str
    message: str
    manifest_path: str = ""
    fiftyone_run_key: str = ""
    source_count: int = 0
    created_count: int = 0
    output_count: int = 0
    available_output_count: int = 0
    missing_output_count: int = 0
    error_count: int = 0
    replay_count: int = 0
    replay_available: bool = False
    output_tag: str = ""
    output_dir: str = ""
    plugin_version: str = ""
    dependency_versions: Mapping[str, str] | None = None
    pipeline_summary: str = ""
    pipeline_config_json: str = ""
    errors_json: str = ""

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        return {
            "run_key": self.run_key,
            "status": self.status,
            "message": self.message,
            "manifest_path": self.manifest_path,
            "fiftyone_run_key": self.fiftyone_run_key,
            "source_count": self.source_count,
            "created_count": self.created_count,
            "output_count": self.output_count,
            "available_output_count": self.available_output_count,
            "missing_output_count": self.missing_output_count,
            "error_count": self.error_count,
            "replay_count": self.replay_count,
            "replay_available": self.replay_available,
            "output_tag": self.output_tag,
            "output_dir": self.output_dir,
            "plugin_version": self.plugin_version,
            "dependency_versions_json": _json_dump(dict(self.dependency_versions or {})),
            "pipeline_summary": self.pipeline_summary,
            "pipeline_config_json": self.pipeline_config_json,
            "errors_json": self.errors_json,
        }


def list_available_run_keys(
    dataset: RunDataset,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[str, ...]:
    """Return known plugin run keys from manifests and FiftyOne custom runs."""

    run_keys = set(_list_manifest_run_keys(dataset.name, storage_root=storage_root))
    run_keys.update(_list_fiftyone_plugin_run_keys(dataset))
    return tuple(sorted(run_keys))


def build_run_summary(
    dataset: RunDataset,
    run_key: str,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> RunSummary:
    """Build a read-only summary for one run key."""

    if not run_key.strip():
        return RunSummary(
            run_key="",
            status=RUN_STATUS_INPUT_REQUIRED,
            message="Select a run key to inspect.",
        )

    store = FileRunStore(dataset.name, storage_root=storage_root)
    fiftyone_run_key = _lookup_fiftyone_run_key(dataset, run_key)
    manifest_path = store.manifest_path(run_key)
    try:
        manifest = store.load_manifest(run_key)
    except MediaIOError as error:
        return _error_summary(
            run_key=run_key,
            error=error,
            manifest_path=manifest_path,
            fiftyone_run_key=fiftyone_run_key,
        )
    except (TypeError, ValueError) as error:
        return RunSummary(
            run_key=run_key,
            status=RUN_STATUS_INVALID,
            message=f"Run manifest is malformed: {error}",
            manifest_path=str(manifest_path),
            fiftyone_run_key=fiftyone_run_key,
        )

    return _manifest_summary(
        manifest,
        run_dir=store.run_dir(manifest.run_key),
        manifest_path=store.manifest_path(manifest.run_key),
        fiftyone_run_key=fiftyone_run_key or _metadata_str(manifest.metadata, "fiftyone_run_key"),
    )


def _list_manifest_run_keys(dataset_name: str, *, storage_root: str | PathLike[str] | None) -> tuple[str, ...]:
    store = FileRunStore(dataset_name, storage_root=storage_root)
    if not store.dataset_dir.exists():
        return ()

    run_keys: list[str] = []
    for manifest_path in sorted(store.dataset_dir.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            manifest = store.load_manifest(manifest_path.parent.name)
        except (MediaIOError, TypeError, ValueError):
            run_keys.append(manifest_path.parent.name)
        else:
            run_keys.append(manifest.run_key)
    return tuple(run_keys)


def _list_fiftyone_plugin_run_keys(dataset: RunDataset) -> tuple[str, ...]:
    run_keys: list[str] = []
    for fiftyone_run_key in dataset.list_runs():
        plugin_run_key = _plugin_run_key_from_fiftyone_run(dataset, str(fiftyone_run_key))
        if plugin_run_key:
            run_keys.append(plugin_run_key)
    return tuple(run_keys)


def _lookup_fiftyone_run_key(dataset: RunDataset, plugin_run_key: str) -> str:
    expected_run_key = build_fiftyone_run_key(plugin_run_key)
    if dataset.has_run(expected_run_key):
        return expected_run_key

    for fiftyone_run_key in dataset.list_runs():
        candidate = str(fiftyone_run_key)
        if _plugin_run_key_from_fiftyone_run(dataset, candidate) == plugin_run_key:
            return candidate
    return ""


def _plugin_run_key_from_fiftyone_run(dataset: RunDataset, fiftyone_run_key: str) -> str:
    try:
        run_info = dataset.get_run_info(fiftyone_run_key)
    except Exception:
        return ""

    config = getattr(run_info, "config", None)
    if getattr(config, "method", None) != FIFTYONE_RUN_METHOD:
        return ""

    raw_plugin_run_key = getattr(config, "plugin_run_key", "")
    return raw_plugin_run_key if isinstance(raw_plugin_run_key, str) else ""


def _error_summary(
    *,
    run_key: str,
    error: MediaIOError,
    manifest_path: Path,
    fiftyone_run_key: str,
) -> RunSummary:
    reason = str(error.context.get("reason", RUN_STATUS_INVALID))
    if reason == "missing_manifest":
        status = RUN_STATUS_MISSING if fiftyone_run_key else RUN_STATUS_NOT_FOUND
        message = "Run manifest is missing."
        if fiftyone_run_key:
            message = "FiftyOne custom run exists, but its manifest file is missing."
    else:
        status = RUN_STATUS_INVALID
        message = error.message

    return RunSummary(
        run_key=run_key,
        status=status,
        message=message,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
    )


def _manifest_summary(
    manifest: RunManifest,
    *,
    run_dir: Path,
    manifest_path: Path,
    fiftyone_run_key: str,
) -> RunSummary:
    available_output_count, missing_output_count = _output_file_counts(run_dir, manifest.output_paths)
    status = RUN_STATUS_OK
    message = "Run manifest loaded."
    if missing_output_count:
        status = RUN_STATUS_STALE
        message = f"Run manifest loaded, but {missing_output_count} output file(s) are missing."

    return RunSummary(
        run_key=manifest.run_key,
        status=status,
        message=message,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        source_count=_counter(manifest.counters, "processed", fallback=len(manifest.source_sample_ids)),
        created_count=_counter(manifest.counters, "created", fallback=len(manifest.created_sample_ids)),
        output_count=_counter(manifest.counters, "outputs", fallback=len(manifest.output_paths)),
        available_output_count=available_output_count,
        missing_output_count=missing_output_count,
        error_count=_counter(manifest.counters, "errors", fallback=len(manifest.errors)),
        replay_count=len(manifest.replay_records),
        replay_available=bool(manifest.replay_records),
        output_tag=_metadata_str(manifest.metadata, "output_tag"),
        output_dir=_metadata_str(manifest.metadata, "output_dir"),
        plugin_version=manifest.plugin_version,
        dependency_versions=manifest.dependency_versions,
        pipeline_summary=summarize_pipeline(manifest.pipeline),
        pipeline_config_json=_json_dump(manifest.pipeline.to_dict()),
        errors_json=_json_dump([dict(error) for error in manifest.errors]),
    )


def _output_file_counts(run_dir: Path, output_paths: tuple[str, ...]) -> tuple[int, int]:
    available_count = 0
    missing_count = 0
    for output_path in output_paths:
        try:
            resolved_path = resolve_manifest_output_path(run_dir, output_path)
        except MediaIOError:
            missing_count += 1
            continue
        if resolved_path.exists():
            available_count += 1
        else:
            missing_count += 1
    return available_count, missing_count


def _counter(counters: Mapping[str, int], name: str, *, fallback: int) -> int:
    value = counters.get(name, fallback)
    return value if isinstance(value, int) else fallback


def _metadata_str(metadata: Mapping[str, Any], name: str) -> str:
    value = metadata.get(name, "")
    return value if isinstance(value, str) else ""


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
