"""Manifest-backed run history without inspecting every generated output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike
from typing import Any, Protocol

from albumentationsx_plugin.core import MediaIOError, RunManifest
from albumentationsx_plugin.hosts.fiftyone.runs import FIFTYONE_RUN_METHOD
from albumentationsx_plugin.hosts.fiftyone.samples import summarize_pipeline
from albumentationsx_plugin.storage.manifest import MANIFEST_FILENAME, FileRunStore


class LibraryDataset(Protocol):
    name: str

    def list_runs(self) -> Sequence[str]: ...

    def get_run_info(self, run_key: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class RunLibraryEntry:
    """One run's identity and recorded outcome, including unavailable manifests."""

    run_key: str
    run_label: str = ""
    created_at: str = ""
    status: str = "missing_manifest"
    execution_scope: str = ""
    source_count: int = 0
    output_count: int = 0
    error_count: int = 0
    pipeline_summary: str = ""
    dependency_summary: str = ""
    cleanup_status: str = ""
    manifest_available: bool = False

    @property
    def display_name(self) -> str:
        return self.run_label or self.run_key

    @property
    def choice_label(self) -> str:
        return f"{self.display_name} | {self.created_at or 'Unknown date'} | {self.status} | {self.run_key}"


def run_created_at(run_key: str, metadata: Mapping[str, object]) -> str:
    """Read a recorded date, falling back to the timestamp in legacy run keys."""

    value = metadata.get("created_at")
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    match = re.search(r"(?:^|-)albumentationsx-(\d{8}T\d{6}Z)-", run_key)
    if match:
        try:
            return datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return ""


def classify_run(manifest: RunManifest) -> str:
    """Distinguish execution outcomes from detailed output availability."""

    if manifest.metadata.get("cleanup_status") == "cleaned":
        return "cleaned"
    execution = manifest.metadata.get("execution_status", "completed")
    if execution in ("cancelled", "running", "dry_run", "preview"):
        return str(execution)
    errors = manifest.counters.get("errors", len(manifest.errors))
    outputs = manifest.counters.get("outputs", max(len(manifest.replay_records), len(manifest.created_sample_ids)))
    if errors or execution == "failed":
        return "partial" if outputs else "failed"
    if execution == "partial":
        return "partial"
    return "completed"


def list_run_library(
    dataset: LibraryDataset,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[RunLibraryEntry, ...]:
    """Merge local manifests and custom run records, newest first.

    Listing reads metadata only; sample queries and output file checks belong to
    the selected run's detailed summary. A broken record cannot hide other runs.
    """

    store = FileRunStore(dataset.name, storage_root=storage_root)
    known: dict[str, str] = {}
    for key in dataset.list_runs():
        try:
            config = dataset.get_run_info(str(key)).config
        except Exception:
            continue
        if getattr(config, "method", None) != FIFTYONE_RUN_METHOD:
            continue
        run_key = getattr(config, "plugin_run_key", "")
        if isinstance(run_key, str) and run_key:
            label = getattr(config, "run_label", "")
            known[run_key] = label if isinstance(label, str) else ""
    for path in store.dataset_dir.glob(f"*/{MANIFEST_FILENAME}"):
        known.setdefault(path.parent.name, "")

    entries = []
    for run_key, label in known.items():
        try:
            manifest = store.load_manifest(run_key)
            if manifest.run_key != run_key:
                raise ValueError("Manifest run key does not match its directory")
        except (MediaIOError, TypeError, ValueError) as error:
            missing = isinstance(error, MediaIOError) and error.context.get("reason") == "missing_manifest"
            entries.append(
                RunLibraryEntry(
                    run_key=run_key,
                    run_label=label,
                    created_at=run_created_at(run_key, {}),
                    status="missing_manifest" if missing else "invalid_manifest",
                )
            )
            continue
        metadata = manifest.metadata
        source_count = metadata.get("source_count", len(manifest.source_sample_ids))
        entries.append(
            RunLibraryEntry(
                run_key=run_key,
                run_label=_text(metadata, "run_label") or label,
                created_at=run_created_at(run_key, metadata),
                status=classify_run(manifest),
                execution_scope=_text(metadata, "execution_scope"),
                source_count=source_count if isinstance(source_count, int) else len(manifest.source_sample_ids),
                output_count=manifest.counters.get(
                    "outputs", max(len(manifest.replay_records), len(manifest.created_sample_ids))
                ),
                error_count=manifest.counters.get("errors", len(manifest.errors)),
                pipeline_summary=summarize_pipeline(manifest.pipeline),
                dependency_summary=", ".join(
                    [
                        f"plugin {manifest.plugin_version}",
                        *(f"{name} {version}" for name, version in sorted(manifest.dependency_versions.items())),
                    ]
                ),
                cleanup_status=_text(metadata, "cleanup_status") or "not cleaned",
                manifest_available=True,
            )
        )
    return tuple(sorted(entries, key=lambda entry: (entry.created_at, entry.run_key), reverse=True))


def _text(metadata: Mapping[str, object], name: str) -> str:
    value = metadata.get(name)
    return value if isinstance(value, str) else ""
