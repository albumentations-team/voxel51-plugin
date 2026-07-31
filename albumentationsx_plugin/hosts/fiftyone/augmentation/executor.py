"""Run the fixed Albumentations MVP slice against FiftyOne image samples."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

import albumentations as A
import fiftyone as fo

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.fixed import (
    FixedImagePipeline,
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
)
from albumentationsx_plugin.core import (
    AugmentationInput,
    AugmentationResult,
    InvalidParameterError,
    JSONDict,
    PipelineConfig,
    PluginError,
    RunManifest,
)
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG, FiftyOneSampleAdapter
from albumentationsx_plugin.storage.images import build_output_image_relative_path, load_rgb_image, write_rgb_image
from albumentationsx_plugin.storage.paths import build_dataset_run_dir, build_run_key


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
    errors: tuple[JSONDict, ...] = ()

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        return {
            "run_key": self.run_key,
            "processed_count": self.processed_count,
            "created_count": self.created_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "dry_run": self.dry_run,
            "output_tag": self.output_tag,
            "output_dir": self.output_dir,
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
) -> FixedAugmentationExecutionResult:
    """Execute the temporary fixed-transform image augmentation flow."""

    config = build_fixed_pipeline_config(params)
    pipeline = create_fixed_image_pipeline(config)
    dry_run = _bool_param(params, "dry_run", default=False)
    run_key = build_run_key()
    run_dir = build_dataset_run_dir(dataset.name, run_key, storage_root=storage_root)
    adapter = FiftyOneSampleAdapter(
        dataset=dataset,
        view=view,
        selected_sample_ids=selected_sample_ids,
        output_tag=output_tag,
    )
    source_inputs = tuple(adapter.iter_inputs())
    if dry_run:
        return FixedAugmentationExecutionResult(
            run_key=run_key,
            processed_count=len(source_inputs),
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag=output_tag,
            output_dir=str(run_dir),
        )

    created_sample_ids: list[str] = []
    output_paths: list[str] = []
    replay_records: list[JSONDict] = []
    errors: list[JSONDict] = []
    skipped_count = 0
    source_sample_ids = tuple(source.sample_id for source in source_inputs)

    for source in source_inputs:
        created_before_sample = len(created_sample_ids)
        for output_index in range(config.outputs_per_sample):
            try:
                _create_one_output(
                    source=source,
                    pipeline=pipeline,
                    config=config,
                    run_dir=run_dir,
                    source_sample_ids=source_sample_ids,
                    output_index=output_index,
                    adapter=adapter,
                    created_sample_ids=created_sample_ids,
                    output_paths=output_paths,
                    replay_records=replay_records,
                )
            except PluginError as error:
                errors.append(_sample_error(source, output_index, error.to_dict()))
        if len(created_sample_ids) == created_before_sample:
            skipped_count += 1

    return FixedAugmentationExecutionResult(
        run_key=run_key,
        processed_count=len(source_inputs),
        created_count=len(created_sample_ids),
        skipped_count=skipped_count,
        error_count=len(errors),
        dry_run=False,
        output_tag=output_tag,
        output_dir=str(run_dir),
        errors=tuple(errors),
    )


def _create_one_output(
    *,
    source: AugmentationInput,
    pipeline: FixedImagePipeline,
    config: PipelineConfig,
    run_dir: Path,
    source_sample_ids: tuple[str, ...],
    output_index: int,
    adapter: FiftyOneSampleAdapter,
    created_sample_ids: list[str],
    output_paths: list[str],
    replay_records: list[JSONDict],
) -> None:
    loaded = load_rgb_image(source.filepath)
    pipeline_result = pipeline.apply(loaded.data)
    relative_path = build_output_image_relative_path(
        source.filepath,
        sample_id=source.sample_id,
        output_index=output_index,
    )
    written_path = write_rgb_image(pipeline_result.image, run_dir, relative_path)
    replay = pipeline_result.replay
    manifest = _manifest(
        run_key=run_dir.name,
        config=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=tuple(created_sample_ids),
        output_paths=(*output_paths, relative_path.as_posix()),
        replay_records=(*replay_records, replay),
    )
    result = AugmentationResult(
        source_sample_id=source.sample_id,
        output_filepath=str(written_path),
        replay=replay,
        metadata={"output_index": output_index, "output_relative_path": relative_path.as_posix()},
    )
    created_sample_ids.append(adapter.create_output_sample(result, manifest))
    output_paths.append(relative_path.as_posix())
    replay_records.append(replay)


def _manifest(
    *,
    run_key: str,
    config: PipelineConfig,
    source_sample_ids: tuple[str, ...],
    created_sample_ids: tuple[str, ...],
    output_paths: tuple[str, ...],
    replay_records: tuple[JSONDict, ...],
) -> RunManifest:
    return RunManifest(
        run_key=run_key,
        plugin_version=albumentationsx_plugin.__version__,
        dependency_versions={
            "albumentationsx": A.__version__,
            "fiftyone": _dependency_version("fiftyone"),
        },
        pipeline=config,
        source_sample_ids=source_sample_ids,
        created_sample_ids=created_sample_ids,
        output_paths=output_paths,
        replay_records=replay_records,
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


def _sample_error(source: AugmentationInput, output_index: int, error: JSONDict) -> JSONDict:
    context = error.get("context")
    if isinstance(context, dict):
        context["sample_id"] = source.sample_id
        context["output_index"] = output_index
    return error
