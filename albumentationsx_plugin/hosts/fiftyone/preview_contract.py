"""Shared FiftyOne preview field names and limits."""

from __future__ import annotations

from typing import Final

PREVIEW_ONLY_FIELD_NAME: Final[str] = "preview_only"
MAX_PREVIEW_SAMPLES: Final[int] = 3
PREVIEW_REQUIRES_SELECTION_ERROR_CODE: Final[str] = "preview_requires_selected_samples"

PREVIEW_FIELD_SOURCE_SAMPLE_ID: Final[str] = "source_sample_id"
PREVIEW_FIELD_SOURCE_FILEPATH: Final[str] = "source_filepath"
PREVIEW_FIELD_SOURCE_IMAGE: Final[str] = "source_image"
PREVIEW_FIELD_OUTPUT_IMAGE: Final[str] = "output_image"
PREVIEW_FIELD_COMPARISON_IMAGE: Final[str] = "comparison_image"
PREVIEW_FIELD_REPLAY_JSON: Final[str] = "replay_json"
PREVIEW_FIELD_LABELS_JSON: Final[str] = "labels_json"
PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON: Final[str] = "annotation_summary_json"
PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON: Final[str] = "annotation_comparison_json"


def preview_field_name(slot_number: int, suffix: str) -> str:
    """Return the stable operator output field name for one preview slot."""

    if slot_number < 1 or slot_number > MAX_PREVIEW_SAMPLES:
        raise ValueError(f"Preview slot must be between 1 and {MAX_PREVIEW_SAMPLES}.")
    return f"preview_{slot_number}_{suffix}"
