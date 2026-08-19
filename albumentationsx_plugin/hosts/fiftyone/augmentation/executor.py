"""Run the fixed Albumentations MVP slice against FiftyOne image samples."""

from __future__ import annotations

import importlib.metadata
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from os import PathLike
from pathlib import Path
from typing import Any

import fiftyone as fo

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.fixed import (
    FixedImagePipeline,
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
)
from albumentationsx_plugin.core import (
    RUN_LABEL_FIELD_NAME,
    RUN_LABEL_SLUG_METADATA_KEY,
    AugmentationInput,
    AugmentationResult,
    InvalidParameterError,
    JSONDict,
    MediaIOError,
    PipelineConfig,
    PluginError,
    RunManifest,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ANNOTATION_PAYLOAD_KEY,
    annotation_run_metadata,
    selected_annotation_fields_from_params,
    target_and_copy_fields,
    target_data_from_annotation_payload,
    transformed_annotation_payload,
    validate_annotation_pipeline_compatibility,
    validate_selected_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_FIELD_NAME,
    selected_execution_scope,
)
from albumentationsx_plugin.hosts.fiftyone.progress import (
    AugmentationProgress,
    NoOpProgressReporter,
    ProgressReporter,
)
from albumentationsx_plugin.hosts.fiftyone.runs import build_fiftyone_run_key, register_fiftyone_run
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG, FiftyOneSampleAdapter
from albumentationsx_plugin.storage.images import build_output_image_relative_path, load_rgb_image, write_rgb_image
from albumentationsx_plugin.storage.manifest import FileRunStore, resolve_manifest_output_path
from albumentationsx_plugin.storage.paths import build_run_key, slugify_run_label

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FixedAugmentationExecutionResult:
    """User-facing summary of one fixed-transform augmentation run."""

    run_key: str
    processed_count: int
    created_count: int
    skipped_count: int
    error_count: int
    dry_run: bool
    output_tag: str
    output_dir: str
    source_scope: str = ""
    manifest_path: str = ""
    fiftyone_run_key: str = ""
    errors: tuple[JSONDict, ...] = ()

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        return {
            "run_key": self.run_key,
            "source_scope": self.source_scope,
            "processed_count": self.processed_count,
            "created_count": self.created_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "dry_run": self.dry_run,
            "output_tag": self.output_tag,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "fiftyone_run_key": self.fiftyone_run_key,
            "errors": [dict(error) for error in self.errors],
        }


def execute_fixed_augmentation(
    *,
    dataset: fo.Dataset,
    params: Mapping[str, object],
    view: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    output_tag: str = DEFAULT_OUTPUT_TAG,
    storage_root: str | PathLike[str] | None = None,
    progress_reporter: ProgressReporter | None = None,
) -> FixedAugmentationExecutionResult:
    """Execute the temporary fixed-transform image augmentation flow."""

    progress_reporter = progress_reporter or NoOpProgressReporter()
    config = build_fixed_pipeline_config(params)
    catalog_provider = AlbuSpecCatalogProvider()
    annotation_selection = selected_annotation_fields_from_params(params, dataset)
    validate_selected_annotation_fields(annotation_selection)
    validate_annotation_pipeline_compatibility(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
    )
    target_fields, copy_fields = target_and_copy_fields(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
    )
    config = replace(config, target_fields=target_fields, copy_fields=copy_fields)
    pipeline = create_fixed_image_pipeline(config)
    dry_run = _bool_param(params, "dry_run", default=False)
    source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    run_label = _optional_str_param(params, RUN_LABEL_FIELD_NAME)
    run_label_slug = slugify_run_label(run_label)
    run_key = build_run_key(run_label=run_label)
    run_store = FileRunStore(dataset_name=dataset.name, storage_root=storage_root)
    run_dir = run_store.run_dir(run_key)
    adapter = FiftyOneSampleAdapter(
        dataset=dataset,
        view=None if source_scope == EXECUTION_SCOPE_ENTIRE_DATASET else view,
        selected_sample_ids=selected_sample_ids,
        selected_label_fields=annotation_selection.selected_field_names,
        include_all_label_fields=False,
        output_tag=output_tag,
    )
    source_inputs = tuple(adapter.iter_inputs())
    source_count = len(source_inputs)
    planned_outputs = source_count * config.outputs_per_sample
    annotation_metadata = annotation_run_metadata(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
    )
    _report_progress(
        progress_reporter,
        stage="starting",
        total_sources=source_count,
        processed_sources=0,
        planned_outputs=planned_outputs,
        created_outputs=0,
        skipped_sources=0,
        errors=0,
    )
    if dry_run:
        _report_progress(
            progress_reporter,
            stage="dry_run_complete",
            total_sources=source_count,
            processed_sources=source_count,
            planned_outputs=planned_outputs,
            created_outputs=0,
            skipped_sources=0,
            errors=0,
            dry_run=True,
        )
        return FixedAugmentationExecutionResult(
            run_key=run_key,
            source_scope=source_scope,
            processed_count=source_count,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag=output_tag,
            output_dir=str(run_dir),
            fiftyone_run_key=build_fiftyone_run_key(run_key),
        )

    created_sample_ids: list[str] = []
    output_paths: list[str] = []
    replay_records: list[JSONDict] = []
    errors: list[JSONDict] = []
    skipped_count = 0
    processed_sources = 0
    source_sample_ids = tuple(source.sample_id for source in source_inputs)
    _save_current_manifest(
        run_store=run_store,
        run_key=run_key,
        config=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=replay_records,
        processed_count=source_count,
        skipped_count=skipped_count,
        errors=errors,
        output_dir=run_dir,
        output_tag=output_tag,
        annotation_metadata=annotation_metadata,
        source_scope=source_scope,
        run_label=run_label,
        run_label_slug=run_label_slug,
    )

    for source_number, source in enumerate(source_inputs, start=1):
        processed_sources = source_number
        created_before_sample = len(created_sample_ids)
        for output_index in range(config.outputs_per_sample):
            checkpoint_current_state = True
            try:
                output = _prepare_one_output(
                    source=source,
                    pipeline=pipeline,
                    config=config,
                    run_dir=run_dir,
                    output_index=output_index,
                )
            except PluginError as error:
                errors.append(_sample_error(source, output_index, error.to_dict()))
                _report_progress(
                    progress_reporter,
                    stage="running",
                    total_sources=source_count,
                    processed_sources=processed_sources,
                    planned_outputs=planned_outputs,
                    created_outputs=len(created_sample_ids),
                    skipped_sources=skipped_count,
                    errors=len(errors),
                )
            else:
                output_paths.append(output.relative_path)
                replay_records.append(output.replay_record)
                manifest = _checkpoint_prepared_output(
                    run_store=run_store,
                    run_key=run_key,
                    config=config,
                    source_sample_ids=source_sample_ids,
                    created_sample_ids=created_sample_ids,
                    output_paths=output_paths,
                    replay_records=replay_records,
                    processed_count=source_count,
                    skipped_count=skipped_count,
                    errors=errors,
                    output_dir=run_dir,
                    output_tag=output_tag,
                    output=output,
                    annotation_metadata=annotation_metadata,
                    source_scope=source_scope,
                    run_label=run_label,
                    run_label_slug=run_label_slug,
                )
                try:
                    created_sample_id = adapter.create_output_sample(output.result, manifest)
                except PluginError as error:
                    errors.append(_sample_error(source, output_index, error.to_dict()))
                    _report_progress(
                        progress_reporter,
                        stage="running",
                        total_sources=source_count,
                        processed_sources=processed_sources,
                        planned_outputs=planned_outputs,
                        created_outputs=len(created_sample_ids),
                        skipped_sources=skipped_count,
                        errors=len(errors),
                    )
                else:
                    created_sample_ids.append(created_sample_id)
                    try:
                        _save_current_manifest(
                            run_store=run_store,
                            run_key=run_key,
                            config=config,
                            source_sample_ids=source_sample_ids,
                            created_sample_ids=created_sample_ids,
                            output_paths=output_paths,
                            replay_records=replay_records,
                            processed_count=source_count,
                            skipped_count=skipped_count,
                            errors=errors,
                            output_dir=run_dir,
                            output_tag=output_tag,
                            annotation_metadata=annotation_metadata,
                            source_scope=source_scope,
                            run_label=run_label,
                            run_label_slug=run_label_slug,
                        )
                    except PluginError:
                        _delete_created_sample(dataset, created_sample_id)
                        created_sample_ids.pop()
                        raise
                    checkpoint_current_state = False
                    _report_progress(
                        progress_reporter,
                        stage="running",
                        total_sources=source_count,
                        processed_sources=processed_sources,
                        planned_outputs=planned_outputs,
                        created_outputs=len(created_sample_ids),
                        skipped_sources=skipped_count,
                        errors=len(errors),
                    )
            if checkpoint_current_state:
                _save_current_manifest(
                    run_store=run_store,
                    run_key=run_key,
                    config=config,
                    source_sample_ids=source_sample_ids,
                    created_sample_ids=created_sample_ids,
                    output_paths=output_paths,
                    replay_records=replay_records,
                    processed_count=source_count,
                    skipped_count=skipped_count,
                    errors=errors,
                    output_dir=run_dir,
                    output_tag=output_tag,
                    annotation_metadata=annotation_metadata,
                    source_scope=source_scope,
                    run_label=run_label,
                    run_label_slug=run_label_slug,
                )
        if len(created_sample_ids) == created_before_sample:
            skipped_count += 1
            _save_current_manifest(
                run_store=run_store,
                run_key=run_key,
                config=config,
                source_sample_ids=source_sample_ids,
                created_sample_ids=created_sample_ids,
                output_paths=output_paths,
                replay_records=replay_records,
                processed_count=source_count,
                skipped_count=skipped_count,
                errors=errors,
                output_dir=run_dir,
                output_tag=output_tag,
                annotation_metadata=annotation_metadata,
                source_scope=source_scope,
                run_label=run_label,
                run_label_slug=run_label_slug,
            )
        _report_progress(
            progress_reporter,
            stage="running",
            total_sources=source_count,
            processed_sources=processed_sources,
            planned_outputs=planned_outputs,
            created_outputs=len(created_sample_ids),
            skipped_sources=skipped_count,
            errors=len(errors),
        )

    final_manifest = _save_current_manifest(
        run_store=run_store,
        run_key=run_key,
        config=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=replay_records,
        processed_count=source_count,
        skipped_count=skipped_count,
        errors=errors,
        output_dir=run_dir,
        output_tag=output_tag,
        annotation_metadata=annotation_metadata,
        source_scope=source_scope,
        run_label=run_label,
        run_label_slug=run_label_slug,
    )
    manifest_path = run_store.manifest_path(run_key)
    fiftyone_run_key = register_fiftyone_run(dataset, final_manifest, manifest_path=manifest_path)
    _report_progress(
        progress_reporter,
        stage="complete",
        total_sources=source_count,
        processed_sources=source_count,
        planned_outputs=planned_outputs,
        created_outputs=len(created_sample_ids),
        skipped_sources=skipped_count,
        errors=len(errors),
    )

    return FixedAugmentationExecutionResult(
        run_key=run_key,
        source_scope=source_scope,
        processed_count=source_count,
        created_count=len(created_sample_ids),
        skipped_count=skipped_count,
        error_count=len(errors),
        dry_run=False,
        output_tag=output_tag,
        output_dir=str(run_dir),
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        errors=tuple(errors),
    )


def _report_progress(
    progress_reporter: ProgressReporter,
    *,
    stage: str,
    total_sources: int,
    processed_sources: int,
    planned_outputs: int,
    created_outputs: int,
    skipped_sources: int,
    errors: int,
    dry_run: bool = False,
) -> None:
    try:
        progress_reporter.report(
            AugmentationProgress(
                stage=stage,
                total_sources=total_sources,
                processed_sources=processed_sources,
                planned_outputs=planned_outputs,
                created_outputs=created_outputs,
                skipped_sources=skipped_sources,
                errors=errors,
                dry_run=dry_run,
            )
        )
    except Exception:
        _LOGGER.debug("Error while reporting augmentation progress", exc_info=True)
        return


def _save_current_manifest(
    *,
    run_store: FileRunStore,
    run_key: str,
    config: PipelineConfig,
    source_sample_ids: tuple[str, ...],
    created_sample_ids: list[str],
    output_paths: list[str],
    replay_records: list[JSONDict],
    processed_count: int,
    skipped_count: int,
    errors: list[JSONDict],
    output_dir: Path,
    output_tag: str,
    annotation_metadata: Mapping[str, object] | None = None,
    source_scope: str = "",
    run_label: str = "",
    run_label_slug: str = "",
) -> RunManifest:
    manifest = _manifest(
        run_key=run_key,
        config=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=tuple(created_sample_ids),
        output_paths=tuple(output_paths),
        replay_records=tuple(replay_records),
        processed_count=processed_count,
        skipped_count=skipped_count,
        errors=tuple(errors),
        output_dir=output_dir,
        output_tag=output_tag,
        annotation_metadata=annotation_metadata,
        source_scope=source_scope,
        run_label=run_label,
        run_label_slug=run_label_slug,
    )
    run_store.save_manifest(manifest)
    return manifest


def _checkpoint_prepared_output(
    *,
    run_store: FileRunStore,
    run_key: str,
    config: PipelineConfig,
    source_sample_ids: tuple[str, ...],
    created_sample_ids: list[str],
    output_paths: list[str],
    replay_records: list[JSONDict],
    processed_count: int,
    skipped_count: int,
    errors: list[JSONDict],
    output_dir: Path,
    output_tag: str,
    output: _PreparedOutput,
    annotation_metadata: Mapping[str, object] | None = None,
    source_scope: str = "",
    run_label: str = "",
    run_label_slug: str = "",
) -> RunManifest:
    try:
        return _save_current_manifest(
            run_store=run_store,
            run_key=run_key,
            config=config,
            source_sample_ids=source_sample_ids,
            created_sample_ids=created_sample_ids,
            output_paths=output_paths,
            replay_records=replay_records,
            processed_count=processed_count,
            skipped_count=skipped_count,
            errors=errors,
            output_dir=output_dir,
            output_tag=output_tag,
            annotation_metadata=annotation_metadata,
            source_scope=source_scope,
            run_label=run_label,
            run_label_slug=run_label_slug,
        )
    except PluginError:
        output_paths.pop()
        replay_records.pop()
        _delete_pre_manifest_output_file(output_dir, output.relative_path)
        raise


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


@dataclass(frozen=True, slots=True)
class _PreparedOutput:
    result: AugmentationResult
    relative_path: str
    replay_record: JSONDict


def _prepare_one_output(
    *,
    source: AugmentationInput,
    pipeline: FixedImagePipeline,
    config: PipelineConfig,
    run_dir: Path,
    output_index: int,
) -> _PreparedOutput:
    loaded = load_rgb_image(source.filepath)
    source_annotation_payload = _source_annotation_payload(source)
    annotation_targets = target_data_from_annotation_payload(
        source_annotation_payload,
        loaded.data.shape,
        label_fields=config.target_fields,
    )
    pipeline_result = pipeline.apply(loaded.data, targets=annotation_targets.values)
    transformed_labels = transformed_annotation_payload(
        source_annotation_payload,
        annotation_targets,
        pipeline_result.targets,
        pipeline_result.image.shape,
        copy_label_fields=config.copy_fields,
    )
    relative_path = build_output_image_relative_path(
        source.filepath,
        sample_id=source.sample_id,
        output_index=output_index,
    )
    written_path = write_rgb_image(pipeline_result.image, run_dir, relative_path)
    replay = pipeline_result.replay
    relative_path_text = relative_path.as_posix()
    return _PreparedOutput(
        result=AugmentationResult(
            source_sample_id=source.sample_id,
            output_filepath=str(written_path),
            labels=transformed_labels,
            replay=replay,
            metadata={
                "output_index": output_index,
                "output_relative_path": relative_path_text,
                "annotations": _annotation_result_metadata(transformed_labels),
            },
        ),
        relative_path=relative_path_text,
        replay_record=_replay_record(
            source=source,
            output_index=output_index,
            relative_path=relative_path_text,
            replay=replay,
            annotation_metadata=_annotation_result_metadata(transformed_labels),
        ),
    )


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
) -> RunManifest:
    counters = {
        "processed": processed_count,
        "created": len(created_sample_ids),
        "skipped": skipped_count,
        "errors": len(errors),
        "outputs": len(output_paths),
    }
    metadata: JSONDict = {
        "output_dir": str(output_dir),
        "output_tag": output_tag,
        "manifest_filename": "manifest.json",
        "fiftyone_run_key": build_fiftyone_run_key(run_key),
        EXECUTION_SCOPE_FIELD_NAME: source_scope,
        "source_count": len(source_sample_ids),
    }
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


def _bool_param(params: Mapping[str, object], parameter_name: str, *, default: bool) -> bool:
    raw_value = params.get(parameter_name, default)
    if not isinstance(raw_value, bool):
        raise InvalidParameterError(
            transform_name="<operator>",
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a boolean.",
            context={"value": raw_value},
        )
    return raw_value


def _optional_str_param(params: Mapping[str, object], parameter_name: str) -> str:
    raw_value = params.get(parameter_name, "")
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raise InvalidParameterError(
            transform_name="<operator>",
            parameter_name=parameter_name,
            message=f"{parameter_name} must be a string.",
            context={"value": raw_value},
        )
    return raw_value if raw_value.strip() else ""


def _sample_error(source: AugmentationInput, output_index: int, error: JSONDict) -> JSONDict:
    context = error.get("context")
    if isinstance(context, dict):
        context["sample_id"] = source.sample_id
        context["output_index"] = output_index
    return error


def _source_annotation_payload(source: AugmentationInput) -> Mapping[str, object]:
    value = source.metadata.get(ANNOTATION_PAYLOAD_KEY)
    return value if isinstance(value, Mapping) else {}


def _annotation_result_metadata(labels: Mapping[str, object]) -> JSONDict:
    value = labels.get("metadata")
    return normalize_json_mapping(value) if isinstance(value, Mapping) else {}


def _replay_record(
    *,
    source: AugmentationInput,
    output_index: int,
    relative_path: str,
    replay: JSONDict,
    annotation_metadata: Mapping[str, object] | None = None,
) -> JSONDict:
    record: JSONDict = {
        "source_sample_id": source.sample_id,
        "output_index": output_index,
        "output_path": relative_path,
        "replay": replay,
    }
    if annotation_metadata:
        record["annotations"] = normalize_json_mapping(annotation_metadata)
    return record
