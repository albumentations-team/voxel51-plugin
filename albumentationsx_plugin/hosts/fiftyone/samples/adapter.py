"""Convert FiftyOne samples to and from host-neutral augmentation DTOs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any

import fiftyone as fo

from albumentationsx_plugin.core import (
    AugmentationInput,
    AugmentationResult,
    HostAdapterError,
    MediaIOError,
    PipelineConfig,
    RunManifest,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ANNOTATION_EXCLUDED_FIELDS_KEY,
    ANNOTATION_PAYLOAD_KEY,
    annotation_payload_from_sample,
    labels_from_annotation_payload,
    resolve_annotation_fields,
)

DEFAULT_OUTPUT_TAG = "albumentationsx-output"
RUN_TAG_PREFIX = "albumentationsx-run"
SOURCE_SAMPLE_ID_FIELD = "albumentationsx_source_sample_id"
RUN_KEY_FIELD = "albumentationsx_run_key"
TRANSFORM_SUMMARY_FIELD = "albumentationsx_transform_summary"
OUTPUT_TAG_FIELD = "albumentationsx_output_tag"
FIFTYONE_HOST_NAME = "fiftyone"
IMAGE_MEDIA_TYPE = "image"


@dataclass(frozen=True, slots=True)
class FiftyOneSampleAdapter:
    """Adapter between FiftyOne sample collections and core augmentation DTOs."""

    dataset: fo.Dataset
    view: Any | None = None
    selected_sample_ids: Sequence[str] = ()
    selected_label_fields: Sequence[str] = ()
    include_all_label_fields: bool = True
    output_tag: str = DEFAULT_OUTPUT_TAG
    _selected_sample_ids: tuple[str, ...] = field(init=False, repr=False)
    _selected_label_fields: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_selected_sample_ids", tuple(str(sample_id) for sample_id in self.selected_sample_ids)
        )
        object.__setattr__(
            self,
            "_selected_label_fields",
            tuple(str(field_name) for field_name in self.selected_label_fields),
        )

    @property
    def host_name(self) -> str:
        """Return the host name required by the host adapter protocol."""

        return FIFTYONE_HOST_NAME

    def iter_inputs(self) -> Iterable[AugmentationInput]:
        """Yield source inputs from the selected samples or current view."""

        collection = self.view if self.view is not None else self.dataset
        _ensure_image_collection(collection)
        label_fields, excluded_label_fields = resolve_annotation_fields(
            self.dataset,
            selected_label_fields=self._selected_label_fields,
            include_all_label_fields=self.include_all_label_fields,
        )

        if not self._selected_sample_ids:
            for sample in collection:
                yield sample_to_augmentation_input(
                    sample,
                    dataset_name=self.dataset.name,
                    selected_label_fields=label_fields,
                    excluded_label_fields=excluded_label_fields,
                )
            return

        samples_by_id: dict[str, fo.Sample] = {}
        selected_ids = set(self._selected_sample_ids)
        for sample in collection:
            sample_id = str(sample.id)
            if sample_id in selected_ids:
                samples_by_id[sample_id] = sample

        missing_ids = tuple(sample_id for sample_id in self._selected_sample_ids if sample_id not in samples_by_id)
        if missing_ids:
            raise HostAdapterError(
                host=FIFTYONE_HOST_NAME,
                message="Selected FiftyOne samples were not found in the active collection.",
                context={
                    "reason": "selected_samples_missing",
                    "dataset_name": self.dataset.name,
                    "sample_ids": list(missing_ids),
                },
            )

        for sample_id in self._selected_sample_ids:
            yield sample_to_augmentation_input(
                samples_by_id[sample_id],
                dataset_name=self.dataset.name,
                selected_label_fields=label_fields,
                excluded_label_fields=excluded_label_fields,
            )

    def create_output_sample(self, result: AugmentationResult, manifest: RunManifest) -> str:
        """Create a FiftyOne sample for one augmentation result."""

        return create_output_sample(
            self.dataset,
            result,
            manifest,
            output_tag=self.output_tag,
        )


def sample_to_augmentation_input(
    sample: fo.Sample,
    *,
    dataset_name: str,
    selected_label_fields: Sequence[str] = (),
    excluded_label_fields: Sequence[Mapping[str, object]] = (),
) -> AugmentationInput:
    """Convert a FiftyOne source sample into a host-neutral input DTO."""

    sample_id = str(sample.id)
    source_path = _require_existing_filepath(sample)
    width, height = _metadata_dimensions(sample)
    annotation_payload = annotation_payload_from_sample(sample, selected_label_fields)
    return AugmentationInput(
        sample_id=sample_id,
        filepath=str(source_path.resolve()),
        media_type=IMAGE_MEDIA_TYPE,
        width=width,
        height=height,
        selected_label_fields=tuple(selected_label_fields),
        metadata={
            "dataset_name": dataset_name,
            "tags": list(sample.tags or ()),
            ANNOTATION_PAYLOAD_KEY: annotation_payload,
            ANNOTATION_EXCLUDED_FIELDS_KEY: [dict(field) for field in excluded_label_fields],
        },
    )


def create_output_sample(
    dataset: fo.Dataset,
    result: AugmentationResult,
    manifest: RunManifest,
    *,
    output_tag: str = DEFAULT_OUTPUT_TAG,
) -> str:
    """Add a new FiftyOne output sample for an augmentation result."""

    _ensure_image_collection(dataset)
    _ensure_result_matches_manifest(result, manifest)
    output_path = _require_existing_output_filepath(result)
    output_sample = fo.Sample(
        filepath=str(output_path.resolve()),
        tags=[output_tag, build_run_tag(manifest.run_key)],
        metadata=fo.ImageMetadata.build_for(str(output_path)),
        **{
            **labels_from_annotation_payload(result.labels),
            SOURCE_SAMPLE_ID_FIELD: result.source_sample_id,
            RUN_KEY_FIELD: manifest.run_key,
            TRANSFORM_SUMMARY_FIELD: summarize_pipeline(manifest.pipeline),
            OUTPUT_TAG_FIELD: output_tag,
        },
    )
    return str(dataset.add_sample(output_sample))


def summarize_pipeline(pipeline: PipelineConfig) -> str:
    """Return a deterministic short transform summary for provenance fields."""

    if not pipeline.transforms:
        return "empty"
    return " -> ".join(_summarize_transform(transform) for transform in pipeline.transforms)


def build_run_tag(run_key: str) -> str:
    """Return the tag used to filter samples created by one run."""

    return f"{RUN_TAG_PREFIX}:{run_key}"


def _summarize_transform(transform: TransformConfig) -> str:
    if not transform.params:
        return transform.name

    params = ", ".join(
        f"{key}={json.dumps(value, sort_keys=True, separators=(',', ':'))}"
        for key, value in sorted(transform.params.items())
    )
    return f"{transform.name}({params})"


def _ensure_image_collection(collection: Any) -> None:
    media_type = getattr(collection, "media_type", None)
    dataset_name = getattr(collection, "name", None)
    if media_type not in (None, IMAGE_MEDIA_TYPE):
        raise HostAdapterError(
            host=FIFTYONE_HOST_NAME,
            message="Only image datasets are supported by the AlbumentationsX MVP adapter.",
            context={
                "reason": "unsupported_media_type",
                "dataset_name": dataset_name,
                "media_type": str(media_type),
            },
        )


def _require_existing_filepath(sample: fo.Sample) -> Path:
    sample_id = str(sample.id)
    filepath = getattr(sample, "filepath", None)
    if not isinstance(filepath, str) or not filepath.strip():
        raise HostAdapterError(
            host=FIFTYONE_HOST_NAME,
            message="FiftyOne source sample does not have a usable filepath.",
            context={
                "reason": "missing_filepath",
                "sample_id": sample_id,
            },
        )

    path = Path(filepath).expanduser()
    if not path.exists():
        raise _media_io_error(
            path,
            "FiftyOne source sample file does not exist.",
            reason="missing_file",
            sample_id=sample_id,
        )
    if not path.is_file():
        raise _media_io_error(
            path,
            "FiftyOne source sample filepath is not a file.",
            reason="not_a_file",
            sample_id=sample_id,
        )

    return path


def _require_existing_output_filepath(result: AugmentationResult) -> Path:
    if result.output_filepath is None:
        raise HostAdapterError(
            host=FIFTYONE_HOST_NAME,
            message="Augmentation result does not define an output filepath.",
            context={
                "reason": "missing_output_filepath",
                "source_sample_id": result.source_sample_id,
            },
        )

    output_path = Path(result.output_filepath).expanduser()
    if not output_path.exists():
        raise _media_io_error(
            output_path,
            "Augmentation output file does not exist.",
            reason="missing_output_file",
            source_sample_id=result.source_sample_id,
        )
    if not output_path.is_file():
        raise _media_io_error(
            output_path,
            "Augmentation output filepath is not a file.",
            reason="not_a_file",
            source_sample_id=result.source_sample_id,
        )

    return output_path


def _ensure_result_matches_manifest(result: AugmentationResult, manifest: RunManifest) -> None:
    if manifest.source_sample_ids and result.source_sample_id not in manifest.source_sample_ids:
        raise HostAdapterError(
            host=FIFTYONE_HOST_NAME,
            message="Augmentation result source sample is not listed in the run manifest.",
            context={
                "reason": "source_sample_not_in_manifest",
                "run_key": manifest.run_key,
                "source_sample_id": result.source_sample_id,
            },
        )


def _metadata_dimensions(sample: fo.Sample) -> tuple[int | None, int | None]:
    metadata = sample.metadata
    width = getattr(metadata, "width", None)
    height = getattr(metadata, "height", None)
    if isinstance(width, int) and isinstance(height, int):
        return width, height
    return None, None


def _media_io_error(
    filepath: str | PathLike[str],
    message: str,
    *,
    reason: str,
    **context: object,
) -> MediaIOError:
    return MediaIOError(
        filepath=str(filepath),
        message=message,
        context={"reason": reason, **context},
    )
