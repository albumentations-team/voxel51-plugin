"""Execute catalog-backed augmentation with recoverable run checkpoints."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from typing import Any

import fiftyone as fo

from albumentationsx_plugin.albumentations_backend.image_pipeline import FixedImagePipeline
from albumentationsx_plugin.core import (
    RUN_EXECUTION_STATUS_CANCELLED,
    RUN_EXECUTION_STATUS_COMPLETED,
    RUN_EXECUTION_STATUS_DRY_RUN,
    RUN_EXECUTION_STATUS_RUNNING,
    RUN_LABEL_FIELD_NAME,
    AugmentationCancelledError,
    AugmentationInput,
    InvalidParameterError,
    JSONDict,
    PipelineConfig,
    PluginError,
)
from albumentationsx_plugin.core.contracts.runs import terminal_execution_status
from albumentationsx_plugin.hosts.fiftyone.augmentation.checkpoints import RunCheckpoint
from albumentationsx_plugin.hosts.fiftyone.augmentation.outputs import PreparedOutput, apply_output, prepare_output
from albumentationsx_plugin.hosts.fiftyone.augmentation.results import (
    FixedAugmentationExecutionResult as FixedAugmentationExecutionResult,
)
from albumentationsx_plugin.hosts.fiftyone.augmentation.runtime import build_fixed_augmentation_runtime
from albumentationsx_plugin.hosts.fiftyone.cancellation import CancellationChecker, NoOpCancellationChecker
from albumentationsx_plugin.hosts.fiftyone.output_metadata import (
    policy_from_annotation_metadata,
)
from albumentationsx_plugin.hosts.fiftyone.progress import (
    AugmentationProgress,
    NoOpProgressReporter,
    ProgressReporter,
)
from albumentationsx_plugin.hosts.fiftyone.runs import build_fiftyone_run_key, register_fiftyone_run
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG
from albumentationsx_plugin.storage.manifest import FileRunStore
from albumentationsx_plugin.storage.paths import build_run_key, slugify_run_label

_LOGGER = logging.getLogger(__name__)


def execute_fixed_augmentation(
    *,
    dataset: fo.Dataset,
    params: Mapping[str, object],
    view: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    output_tag: str = DEFAULT_OUTPUT_TAG,
    storage_root: str | PathLike[str] | None = None,
    progress_reporter: ProgressReporter | None = None,
    cancellation_checker: CancellationChecker | None = None,
) -> FixedAugmentationExecutionResult:
    """Execute the catalog-backed image augmentation flow."""

    progress_reporter = progress_reporter or NoOpProgressReporter()
    cancellation_checker = cancellation_checker or NoOpCancellationChecker()
    runtime = build_fixed_augmentation_runtime(
        dataset=dataset,
        params=params,
        view=view,
        selected_sample_ids=selected_sample_ids,
        output_tag=output_tag,
    )
    config = runtime.config
    pipeline = runtime.pipeline
    source_scope = runtime.source_scope
    adapter = runtime.adapter
    source_inputs = runtime.source_inputs
    annotation_metadata = runtime.annotation_metadata
    external_inputs = runtime.external_inputs
    dry_run = _bool_param(params, "dry_run", default=False)
    run_label = _optional_str_param(params, RUN_LABEL_FIELD_NAME)
    run_label_slug = slugify_run_label(run_label)
    run_key = build_run_key(run_label=run_label)
    run_store = FileRunStore(dataset_name=dataset.name, storage_root=storage_root)
    run_dir = run_store.run_dir(run_key)
    source_count = len(source_inputs)
    planned_outputs = source_count * config.outputs_per_sample
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
        for source in source_inputs:
            for output_index in range(config.outputs_per_sample):
                _raise_if_cancelled(cancellation_checker)
                try:
                    apply_output(
                        source=source,
                        pipeline=pipeline,
                        config=config,
                        output_index=output_index,
                        external_targets=external_inputs.targets_for_source(source.sample_id),
                        external_input_metadata=external_inputs.metadata_for_source(source.sample_id),
                    )
                except PluginError as error:
                    raise PluginError(
                        error.code,
                        f"Sample {source.sample_id}: {error.message}",
                        {**error.context, "sample_id": source.sample_id, "output_index": output_index},
                    ) from error
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
            execution_status=RUN_EXECUTION_STATUS_DRY_RUN,
            fiftyone_run_key=build_fiftyone_run_key(run_key),
            metadata_policy=policy_from_annotation_metadata(annotation_metadata),
        )

    checkpoint = RunCheckpoint(
        run_store=run_store,
        run_key=run_key,
        config=config,
        source_sample_ids=tuple(source.sample_id for source in source_inputs),
        output_dir=run_dir,
        output_tag=output_tag,
        annotation_metadata=annotation_metadata,
        source_scope=source_scope,
        run_label=run_label,
        run_label_slug=run_label_slug,
    )
    checkpoint.save(execution_status=RUN_EXECUTION_STATUS_RUNNING)

    try:
        for source_number, source in enumerate(source_inputs, start=1):
            _raise_if_cancelled(cancellation_checker)
            checkpoint.processed_count = source_number
            created_before_sample = len(checkpoint.created_sample_ids)
            for output_index in range(config.outputs_per_sample):
                checkpoint_current_state = True
                _raise_if_cancelled(cancellation_checker)
                try:
                    output = _prepare_one_output(
                        source=source,
                        pipeline=pipeline,
                        config=config,
                        run_dir=run_dir,
                        output_index=output_index,
                        external_targets=external_inputs.targets_for_source(source.sample_id),
                        external_input_metadata=external_inputs.metadata_for_source(source.sample_id),
                    )
                except PluginError as error:
                    checkpoint.errors.append(_sample_error(source, output_index, error.to_dict()))
                    _report_progress(
                        progress_reporter,
                        stage="running",
                        total_sources=source_count,
                        processed_sources=checkpoint.processed_count,
                        planned_outputs=planned_outputs,
                        created_outputs=len(checkpoint.created_sample_ids),
                        skipped_sources=checkpoint.skipped_count,
                        errors=len(checkpoint.errors),
                    )
                else:
                    checkpoint.output_paths.extend(output.manifest_relative_paths)
                    checkpoint.replay_records.append(output.replay_record)
                    manifest = checkpoint.prepared(output)
                    _raise_if_cancelled(cancellation_checker)
                    error = checkpoint.commit_sample(adapter, output, manifest)
                    if error is not None:
                        checkpoint.errors.append(_sample_error(source, output_index, error.to_dict()))
                        _report_progress(
                            progress_reporter,
                            stage="running",
                            total_sources=source_count,
                            processed_sources=checkpoint.processed_count,
                            planned_outputs=planned_outputs,
                            created_outputs=len(checkpoint.created_sample_ids),
                            skipped_sources=checkpoint.skipped_count,
                            errors=len(checkpoint.errors),
                        )
                    else:
                        checkpoint_current_state = False
                        _report_progress(
                            progress_reporter,
                            stage="running",
                            total_sources=source_count,
                            processed_sources=checkpoint.processed_count,
                            planned_outputs=planned_outputs,
                            created_outputs=len(checkpoint.created_sample_ids),
                            skipped_sources=checkpoint.skipped_count,
                            errors=len(checkpoint.errors),
                        )
                if checkpoint_current_state:
                    checkpoint.save(execution_status=RUN_EXECUTION_STATUS_RUNNING)
            if len(checkpoint.created_sample_ids) == created_before_sample:
                checkpoint.skipped_count += 1
                checkpoint.save(execution_status=RUN_EXECUTION_STATUS_RUNNING)
            _report_progress(
                progress_reporter,
                stage="running",
                total_sources=source_count,
                processed_sources=checkpoint.processed_count,
                planned_outputs=planned_outputs,
                created_outputs=len(checkpoint.created_sample_ids),
                skipped_sources=checkpoint.skipped_count,
                errors=len(checkpoint.errors),
            )
    except AugmentationCancelledError as error:
        return _cancelled_result(
            checkpoint=checkpoint,
            dataset=dataset,
            source_count=source_count,
            planned_outputs=planned_outputs,
            progress_reporter=progress_reporter,
            cancellation_error=error,
        )
    except KeyboardInterrupt:
        return _cancelled_result(
            checkpoint=checkpoint,
            dataset=dataset,
            source_count=source_count,
            planned_outputs=planned_outputs,
            progress_reporter=progress_reporter,
            cancellation_error=AugmentationCancelledError(
                message="Augmentation was interrupted before completion.",
                context={"reason": "keyboard_interrupt"},
            ),
        )

    execution_status = terminal_execution_status(
        succeeded=len(checkpoint.created_sample_ids), errors=len(checkpoint.errors)
    )
    final_manifest = checkpoint.save(processed_count=source_count, execution_status=execution_status)
    manifest_path = run_store.manifest_path(run_key)
    fiftyone_run_key = register_fiftyone_run(dataset, final_manifest, manifest_path=manifest_path)
    _report_progress(
        progress_reporter,
        stage="complete" if execution_status == RUN_EXECUTION_STATUS_COMPLETED else execution_status,
        total_sources=source_count,
        processed_sources=source_count,
        planned_outputs=planned_outputs,
        created_outputs=len(checkpoint.created_sample_ids),
        skipped_sources=checkpoint.skipped_count,
        errors=len(checkpoint.errors),
    )

    return FixedAugmentationExecutionResult(
        run_key=run_key,
        source_scope=source_scope,
        processed_count=source_count,
        created_count=len(checkpoint.created_sample_ids),
        skipped_count=checkpoint.skipped_count,
        error_count=len(checkpoint.errors),
        dry_run=False,
        output_tag=output_tag,
        output_dir=str(run_dir),
        execution_status=execution_status,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        errors=tuple(checkpoint.errors),
        metadata_policy=policy_from_annotation_metadata(annotation_metadata),
    )


def _cancelled_result(
    *,
    dataset: fo.Dataset,
    checkpoint: RunCheckpoint,
    source_count: int,
    planned_outputs: int,
    progress_reporter: ProgressReporter,
    cancellation_error: AugmentationCancelledError,
) -> FixedAugmentationExecutionResult:
    checkpoint.errors.append(cancellation_error.to_dict())
    cancelled_at = _utc_now()
    final_manifest = checkpoint.save(execution_status=RUN_EXECUTION_STATUS_CANCELLED, cancelled_at=cancelled_at)
    manifest_path = checkpoint.run_store.manifest_path(checkpoint.run_key)
    fiftyone_run_key = register_fiftyone_run(dataset, final_manifest, manifest_path=manifest_path)
    _report_progress(
        progress_reporter,
        stage="cancelled",
        total_sources=source_count,
        processed_sources=checkpoint.processed_count,
        planned_outputs=planned_outputs,
        created_outputs=len(checkpoint.created_sample_ids),
        skipped_sources=checkpoint.skipped_count,
        errors=len(checkpoint.errors),
    )
    return FixedAugmentationExecutionResult(
        run_key=checkpoint.run_key,
        source_scope=checkpoint.source_scope,
        processed_count=checkpoint.processed_count,
        created_count=len(checkpoint.created_sample_ids),
        skipped_count=checkpoint.skipped_count,
        error_count=len(checkpoint.errors),
        dry_run=False,
        output_tag=checkpoint.output_tag,
        output_dir=str(checkpoint.output_dir),
        execution_status=RUN_EXECUTION_STATUS_CANCELLED,
        manifest_path=str(manifest_path),
        fiftyone_run_key=fiftyone_run_key,
        errors=tuple(checkpoint.errors),
        metadata_policy=policy_from_annotation_metadata(checkpoint.annotation_metadata),
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


def _prepare_one_output(
    *,
    source: AugmentationInput,
    pipeline: FixedImagePipeline,
    config: PipelineConfig,
    run_dir: Path,
    output_index: int,
    external_targets: Mapping[str, object] | None = None,
    external_input_metadata: Mapping[str, object] | None = None,
) -> PreparedOutput:
    return prepare_output(
        source=source,
        pipeline=pipeline,
        config=config,
        run_dir=run_dir,
        output_index=output_index,
        external_targets=external_targets,
        external_input_metadata=external_input_metadata,
    )


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


def _raise_if_cancelled(cancellation_checker: CancellationChecker) -> None:
    cancellation_checker.raise_if_cancelled()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
