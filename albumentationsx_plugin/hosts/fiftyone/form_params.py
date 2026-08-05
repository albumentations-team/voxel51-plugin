"""Normalize structured FiftyOne form values for the flat execution API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from albumentationsx_plugin.core import MAX_PIPELINE_STEPS

STAGE_PARAMETER_GROUP_PREFIX: Final[str] = "_stage_parameters"


def stage_parameter_group_name(step_number: int) -> str:
    """Return the internal form group name for one stage's parameters."""

    if step_number < 1:
        raise ValueError("step_number must be at least 1")
    return f"{STAGE_PARAMETER_GROUP_PREFIX}_{step_number}"


def flatten_stage_parameter_groups(params: Mapping[str, object]) -> dict[str, object]:
    """Return form params with responsive stage groups flattened."""

    flattened = dict(params)
    for step_number in range(1, MAX_PIPELINE_STEPS + 1):
        group = flattened.pop(stage_parameter_group_name(step_number), None)
        if isinstance(group, Mapping):
            flattened.update(group)
    return flattened
