"""Per-source augmentation output preparation shared by execution modes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from albumentationsx_plugin.albumentations_backend.fixed import FixedImagePipeline
from albumentationsx_plugin.core import AugmentationInput, AugmentationResult, JSONDict, PipelineConfig
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ANNOTATION_PAYLOAD_KEY,
    target_data_from_annotation_payload,
    transformed_annotation_payload,
)
from albumentationsx_plugin.storage.images import (
    RGBArray,
    build_output_image_relative_path,
    load_rgb_image,
    write_rgb_image,
)


@dataclass(frozen=True, slots=True)
class AppliedOutput:
    """In-memory result of applying a pipeline to one source/output pair."""

    source: AugmentationInput
    output_index: int
    source_image: RGBArray
    image: RGBArray
    labels: JSONDict
    replay: JSONDict
    annotation_metadata: JSONDict


@dataclass(frozen=True, slots=True)
class PreparedOutput:
    """Materialized augmentation output ready for sample creation and manifesting."""

    result: AugmentationResult
    relative_path: str
    replay_record: JSONDict


def apply_output(
    *,
    source: AugmentationInput,
    pipeline: FixedImagePipeline,
    config: PipelineConfig,
    output_index: int,
) -> AppliedOutput:
    """Apply a configured pipeline to one source sample without writing files."""

    loaded = load_rgb_image(source.filepath)
    source_payload = annotation_payload_for_source(source)
    annotation_targets = target_data_from_annotation_payload(
        source_payload,
        loaded.data.shape,
        label_fields=config.target_fields,
    )
    pipeline_result = pipeline.apply(loaded.data, targets=annotation_targets.values)
    transformed_labels = normalize_json_mapping(
        transformed_annotation_payload(
            source_payload,
            annotation_targets,
            pipeline_result.targets,
            pipeline_result.image.shape,
            copy_label_fields=config.copy_fields,
        )
    )
    return AppliedOutput(
        source=source,
        output_index=output_index,
        source_image=loaded.data,
        image=pipeline_result.image,
        labels=transformed_labels,
        replay=pipeline_result.replay,
        annotation_metadata=annotation_result_metadata(transformed_labels),
    )


def prepare_output(
    *,
    source: AugmentationInput,
    pipeline: FixedImagePipeline,
    config: PipelineConfig,
    run_dir: Path,
    output_index: int,
) -> PreparedOutput:
    """Apply a pipeline, write its image, and prepare manifest/sample payloads."""

    applied = apply_output(
        source=source,
        pipeline=pipeline,
        config=config,
        output_index=output_index,
    )
    relative_path = build_output_image_relative_path(
        source.filepath,
        sample_id=source.sample_id,
        output_index=output_index,
    )
    written_path = write_rgb_image(applied.image, run_dir, relative_path)
    relative_path_text = relative_path.as_posix()
    return PreparedOutput(
        result=AugmentationResult(
            source_sample_id=source.sample_id,
            output_filepath=str(written_path),
            labels=applied.labels,
            replay=applied.replay,
            metadata={
                "output_index": output_index,
                "output_relative_path": relative_path_text,
                "annotations": applied.annotation_metadata,
            },
        ),
        relative_path=relative_path_text,
        replay_record=build_replay_record(
            source=source,
            output_index=output_index,
            relative_path=relative_path_text,
            replay=applied.replay,
            annotation_metadata=applied.annotation_metadata,
        ),
    )


def annotation_payload_for_source(source: AugmentationInput) -> Mapping[str, object]:
    """Return the serialized source annotation payload from an augmentation input."""

    value = source.metadata.get(ANNOTATION_PAYLOAD_KEY)
    return value if isinstance(value, Mapping) else {}


def annotation_result_metadata(labels: Mapping[str, object]) -> JSONDict:
    """Return JSON-safe annotation diagnostics for a transformed label payload."""

    value = labels.get("metadata")
    return normalize_json_mapping(value) if isinstance(value, Mapping) else {}


def build_replay_record(
    *,
    source: AugmentationInput,
    output_index: int,
    relative_path: str,
    replay: JSONDict,
    annotation_metadata: Mapping[str, object] | None = None,
) -> JSONDict:
    """Return one manifest replay record for a materialized output."""

    record: JSONDict = {
        "source_sample_id": source.sample_id,
        "output_index": output_index,
        "output_path": relative_path,
        "replay": replay,
    }
    if annotation_metadata:
        record["annotations"] = normalize_json_mapping(annotation_metadata)
    return record
