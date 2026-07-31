"""Temporary fixed-transform contract for the first executable MVP slice."""

from __future__ import annotations

from typing import Final

FIXED_TRANSFORM_NAMES: Final[tuple[str, ...]] = (
    "HorizontalFlip",
    "RandomBrightnessContrast",
    "RandomCrop",
)
MAX_OUTPUTS_PER_SAMPLE: Final[int] = 3
DEFAULT_TRANSFORM_PROBABILITY: Final[float] = 1.0
DEFAULT_BRIGHTNESS_RANGE: Final[tuple[float, float]] = (-0.2, 0.2)
DEFAULT_CONTRAST_RANGE: Final[tuple[float, float]] = (-0.2, 0.2)
DEFAULT_CROP_SIZE: Final[int] = 32

__all__ = [
    "DEFAULT_BRIGHTNESS_RANGE",
    "DEFAULT_CONTRAST_RANGE",
    "DEFAULT_CROP_SIZE",
    "DEFAULT_TRANSFORM_PROBABILITY",
    "FIXED_TRANSFORM_NAMES",
    "MAX_OUTPUTS_PER_SAMPLE",
]
