"""Safe cleanup for persisted AlbumentationsX FiftyOne runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from typing import Any, Protocol

from albumentationsx_plugin.core import (
    RUN_CLEANED_AT_METADATA_KEY,
    RUN_CLEANUP_STATUS_CLEANED,
    RUN_CLEANUP_STATUS_METADATA_KEY,
    JSONDict,
    MediaIOError,
    RunManifest,
)
from albumentationsx_plugin.hosts.fiftyone.runs import build_fiftyone_run_key
from albumentationsx_plugin.storage.cleanup import delete_manifest_output_files
from albumentationsx_plugin.storage.manifest import FileRunStore

CLEANUP_STATUS_OK = "ok"
CLEANUP_STATUS_CLEANED = RUN_CLEANUP_STATUS_CLEANED
CLEANUP_STATUS_PARTIAL = "partial"
CLEANUP_STATUS_CONFIRMATION_REQUIRED = "confirmation_required"
CLEANUP_STATUS_MISSING = "missing_manifest"
CLEANUP_STATUS_INVALID = "invalid_manifest"
CLEANUP_STATUS_NOT_FOUND = "not_found"
CLEANUP_STATUS_INPUT_REQUIRED = "input_required"


class CleanupDataset(Protocol):
    """Destructive subset of FiftyOne dataset APIs needed for run cleanup."""

    name: str

    def list_runs(self) -> Sequence[str]:
        """Return registered FiftyOne run keys."""
        ...

    def has_run(self, run_key: str) -> bool:
        """Return whether a FiftyOne run exists."""
        ...

    def delete_run(self, run_key: str) -> None:
        """Delete one FiftyOne custom run."""
        ...

    def select(self, sample_ids: Sequence[str], ordered: bool = False) -> Any:
        """Return a view containing existing sample IDs."""
        ...

    def delete_samples(self, samples_or_ids: Sequence[str]) -> None:
        """Delete samples by ID."""
        ...


@dataclass(frozen=True, slots=True)
class RunCleanupResult:
    """Summary of one cleanup attempt."""

    run_key: str
    status: str
    message: str
    manifest_path: str = ""
    fiftyone_run_key: str = ""
    deleted_sample_count: int = 0
    skipped_sample_count: int = 0
    deleted_file_count: int = 0
    skipped_file_count: int = 0
    failed_file_count: int = 0
    custom_run_deleted: bool = False
    custom_run_missing: bool = False
    confirmed: bool = False
    errors: tuple[JSONDict, ...] = ()

    def to_dict(self) -> JSONDict:
        """Serialize the cleanup result for FiftyOne operator output."""

        return {
            "run_key": self.run_key,
            "status": self.status,
            "message": self.message,
            "manifest_path": self.manifest_path,
            "fiftyone_run_key": self.fiftyone_run_key,
            "deleted_sample_count": self.deleted_sample_count,
            "skipped_sample_count": self.skipped_sample_count,
            "deleted_file_count": self.deleted_file_count,
            "skipped_file_count": self.skipped_file_count,
            "failed_file_count": self.failed_file_count,
            "custom_run_deleted": self.custom_run_deleted,
            "custom_run_missing": self.custom_run_missing,
            "confirmed": self.confirmed,
            "errors_json": _json_dump([dict(error) for error in self.errors]),
        }


def cleanup_run(
    dataset: CleanupDataset,
    run_key: str,
    *,
    confirmed: bool,
    storage_root: str | PathLike[str] | None = None,
) -> RunCleanupResult:
    """Delete generated samples/files for one run after explicit confirmation."""

    if not run_key.strip():
        return RunCleanupResult(
            run_key="",
            status=CLEANUP_STATUS_INPUT_REQUIRED,
            message="Select a run key to delete.",
            confirmed=confirmed,
        )
    if not confirmed:
        return RunCleanupResult(
            run_key=run_key,
            status=CLEANUP_STATUS_CONFIRMATION_REQUIRED,
            message="Cleanup requires explicit confirmation.",
            confirmed=False,
        )

    store = FileRunStore(dataset.name, storage_root=storage_root)
    manifest_path = store.manifest_path(run_key)
    fiftyone_run_key = _fiftyone_run_key(dataset, run_key)
    try:
        manifest = store.load_manifest(run_key)
    except MediaIOError as error:
        return _manifest_error_result(
            run_key=run_key,
            error=error,
            manifest_path=manifest_path,
            fiftyone_run_key=fiftyone_run_key,
            confirmed=confirmed,
        )
    except (TypeError, ValueError) as error:
        return RunCleanupResult(
            run_key=run_key,
            status=CLEANUP_STATUS_INVALID,
            message=f"Run manifest is malformed: {error}",
            manifest_path=str(manifest_path),
            fiftyone_run_key=fiftyone_run_key,
            confirmed=confirmed,
        )

    return _cleanup_loaded_manifest(
        dataset,
        manifest,
        run_store=store,
        run_dir=store.run_dir(manifest.run_key),
        manifest_path=store.manifest_path(manifest.run_key),
        fiftyone_run_key=fiftyone_run_key or build_fiftyone_run_key(manifest.run_key),
        confirmed=confirmed,
    )


def _cleanup_loaded_manifest(
    dataset: CleanupDataset,
    manifest: RunManifest,
    *,
    run_store: FileRunStore,
    run_dir: Path,
    manifest_path: Path,
    fiftyone_run_key: str,
    confirmed: bool,
) -> RunCleanupResult:
    file_cleanup = delete_manifest_output_files(run_dir, manifest.output_paths)
    created_sample_ids = _unique_strings(manifest.created_sample_ids)
    deleted_sample_count, skipped_sample_count = _delete_created_samples(dataset, created_sample_ids)

    custom_run_deleted = False
    custom_run_missing = False
    if file_cleanup.failed_count:
        message = "Cleanup completed partially; some manifest-listed files could not be deleted."
        status = CLEANUP_STATUS_PARTIAL
    else:
        custom_run_deleted, custom_run_missing = _delete_custom_run(dataset, fiftyone_run_key)
        if deleted_sample_count or file_cleanup.deleted_count or custom_run_deleted:
            message = "Cleanup completed."
            status = CLEANUP_STATUS_OK
        else:
            message = "Run was already cleaned; nothing remained to delete."
            status = CLEANUP_STATUS_CLEANED

    result = RunCleanupResult(
        run_key=manifest.run_key,
        status=status,
        message=message,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        deleted_sample_count=deleted_sample_count,
        skipped_sample_count=skipped_sample_count,
        deleted_file_count=file_cleanup.deleted_count,
        skipped_file_count=file_cleanup.skipped_count,
        failed_file_count=file_cleanup.failed_count,
        custom_run_deleted=custom_run_deleted,
        custom_run_missing=custom_run_missing,
        confirmed=confirmed,
        errors=file_cleanup.errors,
    )
    if status not in (CLEANUP_STATUS_OK, CLEANUP_STATUS_CLEANED):
        return result

    metadata_error = _mark_manifest_cleaned(run_store, manifest)
    if metadata_error is None:
        return result
    return replace(
        result,
        status=CLEANUP_STATUS_PARTIAL,
        message="Cleanup completed, but cleanup metadata could not be saved to the manifest.",
        errors=(*result.errors, metadata_error.to_dict()),
    )


def _manifest_error_result(
    *,
    run_key: str,
    error: MediaIOError,
    manifest_path: Path,
    fiftyone_run_key: str,
    confirmed: bool,
) -> RunCleanupResult:
    reason = str(error.context.get("reason", CLEANUP_STATUS_INVALID))
    if reason == "missing_manifest":
        status = CLEANUP_STATUS_MISSING if fiftyone_run_key else CLEANUP_STATUS_NOT_FOUND
        message = "Run manifest is missing."
        if fiftyone_run_key:
            message = "FiftyOne custom run exists, but its manifest file is missing."
    else:
        status = CLEANUP_STATUS_INVALID
        message = error.message

    return RunCleanupResult(
        run_key=run_key,
        status=status,
        message=message,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        confirmed=confirmed,
    )


def _delete_created_samples(dataset: CleanupDataset, sample_ids: tuple[str, ...]) -> tuple[int, int]:
    if not sample_ids:
        return 0, 0

    existing_sample_ids = {str(sample_id) for sample_id in dataset.select(sample_ids).values("id")}
    if existing_sample_ids:
        dataset.delete_samples(tuple(sorted(existing_sample_ids)))
    return len(existing_sample_ids), len(sample_ids) - len(existing_sample_ids)


def _delete_custom_run(dataset: CleanupDataset, fiftyone_run_key: str) -> tuple[bool, bool]:
    if not fiftyone_run_key or not dataset.has_run(fiftyone_run_key):
        return False, True
    dataset.delete_run(fiftyone_run_key)
    return True, False


def _mark_manifest_cleaned(run_store: FileRunStore, manifest: RunManifest) -> MediaIOError | None:
    metadata = dict(manifest.metadata)
    metadata[RUN_CLEANUP_STATUS_METADATA_KEY] = RUN_CLEANUP_STATUS_CLEANED
    metadata.setdefault(RUN_CLEANED_AT_METADATA_KEY, _utc_timestamp())
    try:
        run_store.save_manifest(replace(manifest, metadata=metadata))
    except MediaIOError as error:
        return error
    return None


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fiftyone_run_key(dataset: CleanupDataset, run_key: str) -> str:
    expected_run_key = build_fiftyone_run_key(run_key)
    return expected_run_key if dataset.has_run(expected_run_key) else ""


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
