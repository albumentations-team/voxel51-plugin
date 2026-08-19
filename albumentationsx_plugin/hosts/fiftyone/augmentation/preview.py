"""In-memory FiftyOne augmentation preview execution."""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import fiftyone as fo
from PIL import Image

from albumentationsx_plugin.core import RUN_EXECUTION_STATUS_PREVIEW, JSONDict, PluginError
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.augmentation.outputs import AppliedOutput, apply_output
from albumentationsx_plugin.hosts.fiftyone.augmentation.runtime import build_fixed_augmentation_runtime
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON,
    PREVIEW_FIELD_LABELS_JSON,
    PREVIEW_FIELD_OUTPUT_IMAGE,
    PREVIEW_FIELD_REPLAY_JSON,
    PREVIEW_FIELD_SOURCE_FILEPATH,
    PREVIEW_FIELD_SOURCE_IMAGE,
    PREVIEW_FIELD_SOURCE_SAMPLE_ID,
    PREVIEW_ONLY_FIELD_NAME,
    PREVIEW_REQUIRES_SELECTION_ERROR_CODE,
    preview_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG
from albumentationsx_plugin.storage.images import RGBArray, validate_rgb_array

PREVIEW_NOTE = (
    "Preview generated in memory for up to three selected source samples. "
    "No samples, files, manifests, or FiftyOne custom runs were created."
)


@dataclass(frozen=True, slots=True)
class FixedAugmentationPreviewOutput:
    """One UI-safe in-memory preview result."""

    source_sample_id: str
    source_filepath: str
    source_image: str
    output_image: str
    replay: JSONDict
    labels: JSONDict
    annotation_summary: JSONDict

    def to_dict(self, *, slot_number: int) -> JSONDict:
        """Serialize this output into the flat FiftyOne operator output schema."""

        return {
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_SAMPLE_ID): self.source_sample_id,
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_FILEPATH): self.source_filepath,
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_IMAGE): self.source_image,
            preview_field_name(slot_number, PREVIEW_FIELD_OUTPUT_IMAGE): self.output_image,
            preview_field_name(slot_number, PREVIEW_FIELD_REPLAY_JSON): _json_text(self.replay),
            preview_field_name(slot_number, PREVIEW_FIELD_LABELS_JSON): _json_text(self.labels),
            preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON): _json_text(self.annotation_summary),
        }


@dataclass(frozen=True, slots=True)
class FixedAugmentationPreviewResult:
    """User-facing summary of one in-memory preview execution."""

    source_scope: str
    processed_count: int
    preview_count: int
    skipped_count: int
    error_count: int
    outputs: tuple[FixedAugmentationPreviewOutput, ...]
    errors: tuple[JSONDict, ...] = ()

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        payload: JSONDict = {
            "run_key": "",
            "source_scope": self.source_scope,
            "processed_count": self.processed_count,
            "created_count": 0,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "dry_run": False,
            "execution_status": RUN_EXECUTION_STATUS_PREVIEW,
            "output_tag": "",
            "output_dir": "",
            "manifest_path": "",
            "fiftyone_run_key": "",
            "errors": [dict(error) for error in self.errors],
            PREVIEW_ONLY_FIELD_NAME: True,
            "preview_count": self.preview_count,
            "preview_note": PREVIEW_NOTE,
        }
        for slot_number in range(1, MAX_PREVIEW_SAMPLES + 1):
            if slot_number <= len(self.outputs):
                payload.update(self.outputs[slot_number - 1].to_dict(slot_number=slot_number))
            else:
                payload.update(_empty_preview_slot(slot_number))
        return payload


def execute_fixed_augmentation_preview(
    *,
    dataset: fo.Dataset,
    params: Mapping[str, object],
    view: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    output_tag: str = DEFAULT_OUTPUT_TAG,
    max_preview_samples: int = MAX_PREVIEW_SAMPLES,
) -> FixedAugmentationPreviewResult:
    """Execute a bounded in-memory preview without persisting plugin outputs."""

    if not selected_sample_ids:
        return _requires_selection_result()

    preview_sample_ids = tuple(selected_sample_ids[:MAX_PREVIEW_SAMPLES])
    preview_params = {
        **params,
        EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
    }
    runtime = build_fixed_augmentation_runtime(
        dataset=dataset,
        params=preview_params,
        view=view,
        selected_sample_ids=preview_sample_ids,
        output_tag=output_tag,
    )
    preview_sources = runtime.source_inputs[: max(0, min(max_preview_samples, MAX_PREVIEW_SAMPLES))]
    outputs: list[FixedAugmentationPreviewOutput] = []
    errors: list[JSONDict] = []
    skipped_count = 0

    for source in preview_sources:
        try:
            applied = apply_output(
                source=source,
                pipeline=runtime.pipeline,
                config=runtime.config,
                output_index=0,
            )
        except PluginError as error:
            errors.append(_sample_error(source.sample_id, error.to_dict()))
            skipped_count += 1
        else:
            outputs.append(_preview_output(applied))

    return FixedAugmentationPreviewResult(
        source_scope=runtime.source_scope,
        processed_count=len(preview_sources),
        preview_count=len(outputs),
        skipped_count=skipped_count,
        error_count=len(errors),
        outputs=tuple(outputs),
        errors=tuple(errors),
    )


def _preview_output(applied: AppliedOutput) -> FixedAugmentationPreviewOutput:
    return FixedAugmentationPreviewOutput(
        source_sample_id=applied.source.sample_id,
        source_filepath=applied.source.filepath,
        source_image=_png_data_uri(applied.source_image),
        output_image=_png_data_uri(applied.image),
        replay=normalize_json_mapping(applied.replay),
        labels=normalize_json_mapping(applied.labels),
        annotation_summary=normalize_json_mapping(applied.annotation_metadata),
    )


def _png_data_uri(image: object) -> str:
    array: RGBArray = validate_rgb_array(image)
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _json_text(value: Mapping[str, object]) -> str:
    return json.dumps(normalize_json_mapping(value), indent=2, sort_keys=True)


def _empty_preview_slot(slot_number: int) -> JSONDict:
    return {
        preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_SAMPLE_ID): "",
        preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_FILEPATH): "",
        preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_IMAGE): "",
        preview_field_name(slot_number, PREVIEW_FIELD_OUTPUT_IMAGE): "",
        preview_field_name(slot_number, PREVIEW_FIELD_REPLAY_JSON): "",
        preview_field_name(slot_number, PREVIEW_FIELD_LABELS_JSON): "",
        preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON): "",
    }


def _requires_selection_result() -> FixedAugmentationPreviewResult:
    return FixedAugmentationPreviewResult(
        source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
        processed_count=0,
        preview_count=0,
        skipped_count=0,
        error_count=1,
        outputs=(),
        errors=(
            {
                "code": PREVIEW_REQUIRES_SELECTION_ERROR_CODE,
                "message": "Preview requires one or more selected source samples.",
                "context": {
                    "reason": "empty_selection",
                    "max_preview_samples": MAX_PREVIEW_SAMPLES,
                },
            },
        ),
    )


def _sample_error(sample_id: str, error: JSONDict) -> JSONDict:
    context = error.get("context")
    if isinstance(context, dict):
        context["sample_id"] = sample_id
        context["output_index"] = 0
    return error
