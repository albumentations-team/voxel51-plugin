"""Read-only summaries for persisted AlbumentationsX FiftyOne runs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Protocol

from albumentationsx_plugin.core import (
    RUN_CLEANED_AT_METADATA_KEY,
    RUN_CLEANUP_STATUS_CLEANED,
    RUN_CLEANUP_STATUS_METADATA_KEY,
    RUN_EXECUTION_CANCELLED_AT_METADATA_KEY,
    RUN_EXECUTION_STATUS_CANCELLED,
    RUN_EXECUTION_STATUS_COMPLETED,
    RUN_EXECUTION_STATUS_METADATA_KEY,
    RUN_LABEL_FIELD_NAME,
    RUN_LABEL_SLUG_METADATA_KEY,
    JSONDict,
    MediaIOError,
    RunManifest,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.runs import FIFTYONE_RUN_METHOD, build_fiftyone_run_key
from albumentationsx_plugin.hosts.fiftyone.samples import summarize_pipeline
from albumentationsx_plugin.storage.manifest import (
    MANIFEST_FILENAME,
    FileRunStore,
    resolve_manifest_output_path,
)

RUN_STATUS_OK = "ok"
RUN_STATUS_CLEANED = RUN_CLEANUP_STATUS_CLEANED
RUN_STATUS_STALE = "stale"
RUN_STATUS_MISSING = "missing_manifest"
RUN_STATUS_INVALID = "invalid_manifest"
RUN_STATUS_NOT_FOUND = "not_found"
RUN_STATUS_INPUT_REQUIRED = "input_required"
RUN_STATUS_CANCELLED = RUN_EXECUTION_STATUS_CANCELLED
RUN_OUTPUT_STATUS_AVAILABLE = "available"
RUN_OUTPUT_STATUS_CLEANED = RUN_STATUS_CLEANED
RUN_OUTPUT_STATUS_MISSING_FILE = "missing_output_file"
RUN_OUTPUT_STATUS_MISSING_SAMPLE = "missing_sample"
RUN_OUTPUT_STATUS_MISSING = "missing"


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


class DeletableRunDataset(RunDataset, Protocol):
    """Read-only FiftyOne dataset APIs needed to find runs with cleanup work."""

    def select(self, sample_ids: Sequence[str], ordered: bool = False) -> Any:
        """Return a view containing existing sample IDs."""
        ...


@dataclass(frozen=True, slots=True)
class RunOutputSummary:
    """Read-only summary of one manifest-listed generated output."""

    key: str
    position: int
    label: str
    status: str
    source_sample_id: str = ""
    output_index: int = 0
    output_path: str = ""
    generated_sample_id: str = ""
    generated_sample_available: bool = False
    output_file_available: bool = False
    replay_available: bool = False
    replay_record: Mapping[str, object] | None = None

    def to_dict(self) -> JSONDict:
        """Serialize the generated output for FiftyOne operator output."""

        return {
            "key": self.key,
            "position": self.position,
            "label": self.label,
            "status": self.status,
            "source_sample_id": self.source_sample_id,
            "output_index": self.output_index,
            "output_path": self.output_path,
            "generated_sample_id": self.generated_sample_id,
            "generated_sample_available": self.generated_sample_available,
            "output_file_available": self.output_file_available,
            "replay_available": self.replay_available,
            "replay_record": normalize_json_mapping(self.replay_record),
        }


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Read-only summary of a persisted AlbumentationsX run."""

    run_key: str
    status: str
    message: str
    manifest_path: str = ""
    fiftyone_run_key: str = ""
    cleanup_status: str = ""
    cleaned_at: str = ""
    execution_status: str = ""
    cancelled_at: str = ""
    run_label: str = ""
    run_label_slug: str = ""
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
    generated_outputs: tuple[RunOutputSummary, ...] = ()
    selected_output_key: str = ""

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        selected_output = self.selected_output
        return {
            "run_key": self.run_key,
            "status": self.status,
            "message": self.message,
            "manifest_path": self.manifest_path,
            "fiftyone_run_key": self.fiftyone_run_key,
            "cleanup_status": self.cleanup_status,
            "cleaned_at": self.cleaned_at,
            "execution_status": self.execution_status,
            "cancelled_at": self.cancelled_at,
            "run_label": self.run_label,
            "run_label_slug": self.run_label_slug,
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
            "generated_sample_ids_json": _json_dump(self.generated_sample_ids),
            "available_generated_sample_ids_json": _json_dump(self.available_generated_sample_ids),
            "generated_outputs_json": _json_dump([output.to_dict() for output in self.generated_outputs]),
            "selected_output_key": selected_output.key if selected_output else "",
            "selected_output_status": selected_output.status if selected_output else "",
            "selected_source_sample_id": selected_output.source_sample_id if selected_output else "",
            "selected_generated_sample_id": selected_output.generated_sample_id if selected_output else "",
            "selected_output_index": selected_output.output_index if selected_output else 0,
            "selected_output_path": selected_output.output_path if selected_output else "",
            "selected_output_available": _selected_output_available(selected_output),
            "selected_replay_json": _json_dump(dict(selected_output.replay_record or {}) if selected_output else {}),
        }

    @property
    def generated_sample_ids(self) -> tuple[str, ...]:
        """Return manifest-listed created sample IDs in output order."""

        return tuple(output.generated_sample_id for output in self.generated_outputs if output.generated_sample_id)

    @property
    def available_generated_sample_ids(self) -> tuple[str, ...]:
        """Return generated sample IDs still present in the active dataset."""

        return tuple(
            output.generated_sample_id
            for output in self.generated_outputs
            if output.generated_sample_id and output.generated_sample_available
        )

    @property
    def selected_output(self) -> RunOutputSummary | None:
        """Return the selected generated output, defaulting to the first one."""

        if not self.generated_outputs:
            return None
        if self.selected_output_key:
            for output in self.generated_outputs:
                if output.key == self.selected_output_key:
                    return output
        return self.generated_outputs[0]


def list_available_run_keys(
    dataset: RunDataset,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[str, ...]:
    """Return known plugin run keys from manifests and FiftyOne custom runs."""

    run_keys = set(_list_manifest_run_keys(dataset.name, storage_root=storage_root))
    run_keys.update(_list_fiftyone_plugin_run_keys(dataset))
    return tuple(sorted(run_keys))


def list_deletable_run_keys(
    dataset: DeletableRunDataset,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[str, ...]:
    """Return plugin run keys that still have cleanup work available."""

    run_keys = set(_list_fiftyone_plugin_run_keys(dataset))
    run_keys.update(_list_deletable_manifest_run_keys(dataset, storage_root=storage_root))
    return tuple(sorted(run_keys))


def build_run_summary(
    dataset: RunDataset,
    run_key: str,
    *,
    storage_root: str | PathLike[str] | None = None,
    selected_output_key: str = "",
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
        dataset=dataset,
        run_dir=store.run_dir(manifest.run_key),
        manifest_path=store.manifest_path(manifest.run_key),
        fiftyone_run_key=fiftyone_run_key or _metadata_str(manifest.metadata, "fiftyone_run_key"),
        selected_output_key=selected_output_key,
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


def _list_deletable_manifest_run_keys(
    dataset: DeletableRunDataset,
    *,
    storage_root: str | PathLike[str] | None,
) -> tuple[str, ...]:
    store = FileRunStore(dataset.name, storage_root=storage_root)
    if not store.dataset_dir.exists():
        return ()

    run_keys: list[str] = []
    for manifest_path in sorted(store.dataset_dir.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            manifest = store.load_manifest(manifest_path.parent.name)
        except (MediaIOError, TypeError, ValueError):
            continue
        if _manifest_has_deletable_artifacts(dataset, manifest, run_dir=store.run_dir(manifest.run_key)):
            run_keys.append(manifest.run_key)
    return tuple(run_keys)


def _manifest_has_deletable_artifacts(
    dataset: DeletableRunDataset,
    manifest: RunManifest,
    *,
    run_dir: Path,
) -> bool:
    if _lookup_fiftyone_run_key(dataset, manifest.run_key):
        return True
    if _existing_created_sample_count(dataset, manifest.created_sample_ids):
        return True

    available_output_count, _missing_output_count = _output_file_counts(run_dir, manifest.output_paths)
    return available_output_count > 0


def _existing_created_sample_count(dataset: DeletableRunDataset, sample_ids: tuple[str, ...]) -> int:
    return len(_existing_created_sample_ids(dataset, sample_ids))


def _existing_created_sample_ids(dataset: RunDataset, sample_ids: Sequence[str]) -> tuple[str, ...]:
    if not sample_ids:
        return ()
    select = getattr(dataset, "select", None)
    if not callable(select):
        return ()
    try:
        view = select(tuple(sample_ids))
        values = getattr(view, "values", None)
        if not callable(values):
            return ()
        raw_existing_ids = values("id")
        if not isinstance(raw_existing_ids, Sequence) or isinstance(raw_existing_ids, str):
            return ()
        existing_ids = {str(sample_id) for sample_id in raw_existing_ids}
    except Exception:
        return ()
    return tuple(sample_id for sample_id in sample_ids if sample_id in existing_ids)


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
    dataset: RunDataset,
    run_dir: Path,
    manifest_path: Path,
    fiftyone_run_key: str,
    selected_output_key: str,
) -> RunSummary:
    available_output_count, missing_output_count = _output_file_counts(run_dir, manifest.output_paths)
    cleanup_status = _metadata_str(manifest.metadata, RUN_CLEANUP_STATUS_METADATA_KEY)
    cleaned_at = _metadata_str(manifest.metadata, RUN_CLEANED_AT_METADATA_KEY)
    execution_status = _execution_status(manifest.metadata)
    cancelled_at = _metadata_str(manifest.metadata, RUN_EXECUTION_CANCELLED_AT_METADATA_KEY)
    status = RUN_STATUS_OK
    message = "Run manifest loaded."
    if cleanup_status == RUN_CLEANUP_STATUS_CLEANED:
        status = RUN_STATUS_CLEANED
        message = "Run has been cleaned; manifest is retained for audit."
    elif missing_output_count:
        status = RUN_STATUS_STALE
        message = f"Run manifest loaded, but {missing_output_count} output file(s) are missing."
    elif execution_status == RUN_EXECUTION_STATUS_CANCELLED:
        status = RUN_STATUS_CANCELLED
        message = "Run was cancelled; retained partial outputs can be inspected or cleaned up."

    generated_outputs = _run_outputs(
        dataset,
        manifest,
        run_dir=run_dir,
        cleanup_status=cleanup_status,
    )
    return RunSummary(
        run_key=manifest.run_key,
        status=status,
        message=message,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        cleanup_status=cleanup_status,
        cleaned_at=cleaned_at,
        execution_status=execution_status,
        cancelled_at=cancelled_at,
        run_label=_metadata_str(manifest.metadata, RUN_LABEL_FIELD_NAME),
        run_label_slug=_metadata_str(manifest.metadata, RUN_LABEL_SLUG_METADATA_KEY),
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
        generated_outputs=generated_outputs,
        selected_output_key=selected_output_key,
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


def _run_outputs(
    dataset: RunDataset,
    manifest: RunManifest,
    *,
    run_dir: Path,
    cleanup_status: str,
) -> tuple[RunOutputSummary, ...]:
    available_sample_ids = set(_existing_created_sample_ids(dataset, manifest.created_sample_ids))
    output_count = max(len(manifest.output_paths), len(manifest.replay_records), len(manifest.created_sample_ids))
    outputs: list[RunOutputSummary] = []
    for position in range(output_count):
        replay_record = _sequence_mapping(manifest.replay_records, position)
        output_path = _sequence_str(manifest.output_paths, position) or _mapping_str(replay_record, "output_path")
        source_sample_id = _mapping_str(replay_record, "source_sample_id")
        output_index = _mapping_int(replay_record, "output_index", fallback=position)
        generated_sample_id = _sequence_str(manifest.created_sample_ids, position)
        output_file_available = _output_file_available(run_dir, output_path)
        generated_sample_available = bool(generated_sample_id and generated_sample_id in available_sample_ids)
        status = _run_output_status(
            cleanup_status=cleanup_status,
            output_path=output_path,
            output_file_available=output_file_available,
            generated_sample_id=generated_sample_id,
            generated_sample_available=generated_sample_available,
        )
        key = _run_output_key(
            position=position,
            source_sample_id=source_sample_id,
            output_index=output_index,
            output_path=output_path,
        )
        outputs.append(
            RunOutputSummary(
                key=key,
                position=position,
                label=_run_output_label(
                    position=position,
                    source_sample_id=source_sample_id,
                    output_index=output_index,
                    output_path=output_path,
                    status=status,
                ),
                status=status,
                source_sample_id=source_sample_id,
                output_index=output_index,
                output_path=output_path,
                generated_sample_id=generated_sample_id,
                generated_sample_available=generated_sample_available,
                output_file_available=output_file_available,
                replay_available=bool(replay_record),
                replay_record=replay_record,
            )
        )
    return tuple(outputs)


def _output_file_available(run_dir: Path, output_path: str) -> bool:
    if not output_path:
        return False
    try:
        resolved_path = resolve_manifest_output_path(run_dir, output_path)
    except MediaIOError:
        return False
    return resolved_path.exists()


def _run_output_status(
    *,
    cleanup_status: str,
    output_path: str,
    output_file_available: bool,
    generated_sample_id: str,
    generated_sample_available: bool,
) -> str:
    if cleanup_status == RUN_CLEANUP_STATUS_CLEANED:
        return RUN_OUTPUT_STATUS_CLEANED
    if output_path and not output_file_available:
        return RUN_OUTPUT_STATUS_MISSING_FILE
    if output_file_available and (not generated_sample_id or generated_sample_available):
        return RUN_OUTPUT_STATUS_AVAILABLE
    if generated_sample_id and not generated_sample_available:
        return RUN_OUTPUT_STATUS_MISSING_SAMPLE
    return RUN_OUTPUT_STATUS_MISSING


def _run_output_key(
    *,
    position: int,
    source_sample_id: str,
    output_index: int,
    output_path: str,
) -> str:
    return "|".join((str(position), source_sample_id, str(output_index), output_path))


def _run_output_label(
    *,
    position: int,
    source_sample_id: str,
    output_index: int,
    output_path: str,
    status: str,
) -> str:
    source = source_sample_id or "unknown-source"
    output = output_path or "unknown-output"
    return f"#{position + 1} source={source} output_index={output_index} status={status} path={output}"


def _sequence_str(values: Sequence[str], position: int) -> str:
    if 0 <= position < len(values):
        value = values[position]
        return value if isinstance(value, str) else ""
    return ""


def _sequence_mapping(values: Sequence[Mapping[str, object]], position: int) -> Mapping[str, object]:
    if 0 <= position < len(values):
        value = values[position]
        return value if isinstance(value, Mapping) else {}
    return {}


def _mapping_str(value: Mapping[str, object], name: str) -> str:
    raw_value = value.get(name, "")
    return raw_value if isinstance(raw_value, str) else ""


def _mapping_int(value: Mapping[str, object], name: str, *, fallback: int) -> int:
    raw_value = value.get(name, fallback)
    return raw_value if isinstance(raw_value, int) else fallback


def _selected_output_available(output: RunOutputSummary | None) -> bool:
    if output is None:
        return False
    return output.generated_sample_available and output.output_file_available


def _counter(counters: Mapping[str, int], name: str, *, fallback: int) -> int:
    value = counters.get(name, fallback)
    return value if isinstance(value, int) else fallback


def _metadata_str(metadata: Mapping[str, Any], name: str) -> str:
    value = metadata.get(name, "")
    return value if isinstance(value, str) else ""


def _execution_status(metadata: Mapping[str, Any]) -> str:
    value = _metadata_str(metadata, RUN_EXECUTION_STATUS_METADATA_KEY)
    return value if value else RUN_EXECUTION_STATUS_COMPLETED


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
