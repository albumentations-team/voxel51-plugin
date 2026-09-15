"""Read safe defaults for augmentation form controls."""

from __future__ import annotations

from albumentationsx_plugin.core import (
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
)


def _selected_step_count(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_PIPELINE_STEPS:
        return raw_value
    return 1


def _selected_outputs_per_sample(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_OUTPUTS_PER_SAMPLE:
        return raw_value
    return 1


def _selected_bool(raw_value: object, *, default: bool) -> bool:
    return raw_value if isinstance(raw_value, bool) else default


def _selected_int(raw_value: object, *, default: int, min_value: int, max_value: int) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and min_value <= raw_value <= max_value:
        return raw_value
    return default


def _selected_string(raw_value: object) -> str:
    return raw_value if isinstance(raw_value, str) else ""
