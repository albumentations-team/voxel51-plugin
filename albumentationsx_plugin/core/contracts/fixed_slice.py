"""Temporary fixed-transform contract for the first executable MVP slice."""

from __future__ import annotations

from typing import Final

FIXED_TRANSFORM_NAMES: Final[tuple[str, ...]] = (
    "HorizontalFlip",
    "RandomBrightnessContrast",
    "RandomCrop",
)
MAX_PIPELINE_STEPS: Final[int] = 3
MAX_OUTPUTS_PER_SAMPLE: Final[int] = 3
DEFAULT_TRANSFORM_PROBABILITY: Final[float] = 1.0
DEFAULT_BRIGHTNESS_RANGE: Final[tuple[float, float]] = (-0.2, 0.2)
DEFAULT_CONTRAST_RANGE: Final[tuple[float, float]] = (-0.2, 0.2)
DEFAULT_CROP_SIZE: Final[int] = 32
PIPELINE_STEP_COUNT_FIELD_NAME: Final[str] = "pipeline_step_count"


def pipeline_step_field_name(step_number: int, field_name: str) -> str:
    """Return the operator param name for one pipeline step field."""

    if step_number < 1:
        raise ValueError("step_number must be at least 1")
    if step_number == 1:
        return field_name
    return f"step_{step_number}_{field_name}"


__all__ = [
    "DEFAULT_BRIGHTNESS_RANGE",
    "DEFAULT_CONTRAST_RANGE",
    "DEFAULT_CROP_SIZE",
    "DEFAULT_TRANSFORM_PROBABILITY",
    "FIXED_TRANSFORM_NAMES",
    "MAX_PIPELINE_STEPS",
    "MAX_OUTPUTS_PER_SAMPLE",
    "PIPELINE_STEP_COUNT_FIELD_NAME",
    "pipeline_step_field_name",
]
