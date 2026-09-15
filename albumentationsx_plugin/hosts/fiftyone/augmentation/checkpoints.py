"""Run state and ordered manifest/sample checkpoints with rollback."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import fiftyone as fo

import albumentationsx_plugin
from albumentationsx_plugin.core import (
    RUN_EXECUTION_CANCELLED_AT_METADATA_KEY,
    RUN_EXECUTION_STATUS_METADATA_KEY,
    RUN_EXECUTION_STATUS_RUNNING,
    RUN_LABEL_FIELD_NAME,
    RUN_LABEL_SLUG_METADATA_KEY,
    JSONDict,
    MediaIOError,
    PipelineConfig,
    PluginError,
    RunManifest,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.augmentation.outputs import PreparedOutput
from albumentationsx_plugin.hosts.fiftyone.execution_scope import EXECUTION_SCOPE_FIELD_NAME
from albumentationsx_plugin.hosts.fiftyone.runs import build_fiftyone_run_key
from albumentationsx_plugin.hosts.fiftyone.samples import FiftyOneSampleAdapter
from albumentationsx_plugin.storage.manifest import FileRunStore, resolve_manifest_output_path


@dataclass(slots=True)
class RunCheckpoint:
    """Own mutable run counters and persist the files-before-samples contract."""

    run_store: FileRunStore
    run_key: str
    config: PipelineConfig
    source_sample_ids: tuple[str, ...]
    output_dir: Path
    output_tag: str
    annotation_metadata: Mapping[str, object]
    source_scope: str
    run_label: str
    run_label_slug: str
    created_sample_ids: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    replay_records: list[JSONDict] = field(default_factory=list)
    errors: list[JSONDict] = field(default_factory=list)
    processed_count: int = 0
    skipped_count: int = 0

    def save(
        self,
        *,
        execution_status: str = RUN_EXECUTION_STATUS_RUNNING,
        cancelled_at: str = "",
        processed_count: int | None = None,
    ) -> RunManifest:
        """Persist a snapshot without handing mutable run state to storage."""
        if processed_count is not None:
            self.processed_count = processed_count
        manifest = _manifest(
            run_key=self.run_key,
            config=self.config,
            source_sample_ids=self.source_sample_ids,
            created_sample_ids=tuple(self.created_sample_ids),
            output_paths=tuple(self.output_paths),
            replay_records=tuple(self.replay_records),
            processed_count=self.processed_count,
            skipped_count=self.skipped_count,
            errors=tuple(self.errors),
            output_dir=self.output_dir,
            output_tag=self.output_tag,
            annotation_metadata=self.annotation_metadata,
            source_scope=self.source_scope,
            run_label=self.run_label,
            run_label_slug=self.run_label_slug,
            execution_status=execution_status,
            cancelled_at=cancelled_at,
        )
        self.run_store.save_manifest(manifest)
        return manifest

    def prepared(self, output: PreparedOutput) -> RunManifest:
        """Checkpoint written files before exposing their corresponding sample."""
        try:
            return self.save()
        except PluginError:
            _rollback_output_paths(self.output_paths, output)
            self.replay_records.pop()
            _delete_pre_manifest_output_files(self.output_dir, output.manifest_relative_paths)
            raise

    def commit_sample(
        self, adapter: FiftyOneSampleAdapter, output: PreparedOutput, manifest: RunManifest
    ) -> PluginError | None:
        """Create and checkpoint one sample; roll it back if the checkpoint fails.

        A sample creation error is returned for per-output reporting. A persistence
        failure propagates: continuing would expose samples missing from the manifest.
        """
        try:
            sample_id = adapter.create_output_sample(output.result, manifest)
        except PluginError as error:
            return error
        self.created_sample_ids.append(sample_id)
        try:
            self.save()
        except PluginError:
            _delete_created_sample(adapter.dataset, sample_id)
            self.created_sample_ids.pop()
            raise
        return None


def _manifest(
    *,
    run_key: str,
    config: PipelineConfig,
    source_sample_ids: tuple[str, ...],
    created_sample_ids: tuple[str, ...],
    output_paths: tuple[str, ...],
    replay_records: tuple[JSONDict, ...],
    processed_count: int,
    skipped_count: int,
    errors: tuple[JSONDict, ...],
    output_dir: Path,
    output_tag: str,
    annotation_metadata: Mapping[str, object] | None = None,
    source_scope: str = "",
    run_label: str = "",
    run_label_slug: str = "",
    execution_status: str = RUN_EXECUTION_STATUS_RUNNING,
    cancelled_at: str = "",
) -> RunManifest:
    counters = {
        "processed": processed_count,
        "created": len(created_sample_ids),
        "skipped": skipped_count,
        "errors": len(errors),
        "outputs": len(replay_records),
    }
    if len(output_paths) != len(replay_records):
        counters["output_files"] = len(output_paths)
    metadata: JSONDict = {
        "output_dir": str(output_dir),
        "output_tag": output_tag,
        "manifest_filename": "manifest.json",
        "fiftyone_run_key": build_fiftyone_run_key(run_key),
        EXECUTION_SCOPE_FIELD_NAME: source_scope,
        "source_count": len(source_sample_ids),
        RUN_EXECUTION_STATUS_METADATA_KEY: execution_status,
    }
    if cancelled_at:
        metadata[RUN_EXECUTION_CANCELLED_AT_METADATA_KEY] = cancelled_at
    if annotation_metadata is not None:
        metadata["annotations"] = normalize_json_mapping(annotation_metadata)
    if run_label_slug:
        metadata[RUN_LABEL_FIELD_NAME] = run_label
        metadata[RUN_LABEL_SLUG_METADATA_KEY] = run_label_slug

    return RunManifest(
        run_key=run_key,
        plugin_version=albumentationsx_plugin.__version__,
        dependency_versions={
            "albumentationsx": _dependency_version("albumentationsx"),
            "albu-spec": _dependency_version("albu-spec"),
            "fiftyone": _dependency_version("fiftyone"),
        },
        pipeline=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=replay_records,
        counters=counters,
        errors=errors,
        metadata=metadata,
    )


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _rollback_output_paths(output_paths: list[str], output: PreparedOutput) -> None:
    for _relative_path in output.manifest_relative_paths:
        output_paths.pop()


def _delete_pre_manifest_output_files(run_dir: Path, relative_paths: Sequence[str]) -> None:
    for relative_path in relative_paths:
        _delete_pre_manifest_output_file(run_dir, relative_path)


def _delete_pre_manifest_output_file(run_dir: Path, relative_path: str) -> None:
    try:
        resolve_manifest_output_path(run_dir, relative_path).unlink(missing_ok=True)
    except (MediaIOError, OSError):
        return


def _delete_created_sample(dataset: fo.Dataset, sample_id: str) -> None:
    try:
        dataset.delete_samples((sample_id,))
    except Exception:
        return
