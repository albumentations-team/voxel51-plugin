"""Read augmentation operator values and dependency errors."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from albumentationsx_plugin.hosts.fiftyone.dependencies import (
    is_known_runtime_dependency,
    runtime_dependency_package_name,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    execution_params as effective_editor_params,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    flatten_fiftyone_form_groups,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_ONLY_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    PREVIEW_ONLY_FIELD_NAME,
)


def _ctx_params(ctx: Any | None) -> dict[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_fiftyone_form_groups(params) if isinstance(params, Mapping) else {}


def _params_dict(params: object) -> dict[str, object]:
    return dict(params) if isinstance(params, Mapping) else {}


def _json_dump(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _dry_run_param(params: object) -> bool:
    return isinstance(params, dict) and params.get("dry_run") is True


def _preview_only_param(params: object) -> bool:
    return isinstance(params, dict) and params.get(PREVIEW_ONLY_FIELD_NAME) is True


def _save_preset_only_param(params: object) -> bool:
    return isinstance(params, dict) and params.get(SAVE_PRESET_ONLY_FIELD_NAME) is True


def _preview_only_from_ctx(ctx: Any | None) -> bool:
    return _preview_only_param(effective_editor_params(_ctx_params(ctx)))


def _is_missing_runtime_dependency(error: ModuleNotFoundError) -> bool:
    return is_known_runtime_dependency(error)


def _dependency_package_name(error: ModuleNotFoundError) -> str:
    return runtime_dependency_package_name(error)


def _missing_dependency_message(error: ModuleNotFoundError) -> str:
    package_name = _dependency_package_name(error)
    return (
        f"Install the '{package_name}' package in the active FiftyOne Python environment, then reload the FiftyOne App."
    )
