"""Legacy selector fields, storage overrides, and preset compatibility exports."""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from typing import Final

from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import (
    operator_params_from_pipeline as operator_params_from_pipeline,
)
from albumentationsx_plugin.hosts.fiftyone.run_library import (
    list_previous_run_preset_keys as list_previous_run_preset_keys,
)

PREVIOUS_RUN_KEY_FIELD_NAME: Final[str] = "previous_run_key"
STORAGE_ROOT_PARAM_NAME: Final[str] = "_storage_root"


def selected_previous_run_key(params: Mapping[str, object]) -> str:
    """Return the selected previous run key, if any."""

    value = params.get(PREVIOUS_RUN_KEY_FIELD_NAME)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def storage_root_from_params(params: Mapping[str, object]) -> str | PathLike[str] | None:
    """Return the test-only storage root override from operator params."""

    value = params.get(STORAGE_ROOT_PARAM_NAME)
    if isinstance(value, str):
        return value
    return value if isinstance(value, PathLike) else None


__all__ = [
    "PREVIOUS_RUN_KEY_FIELD_NAME",
    "STORAGE_ROOT_PARAM_NAME",
    "list_previous_run_preset_keys",
    "operator_params_from_pipeline",
    "selected_previous_run_key",
    "storage_root_from_params",
]
