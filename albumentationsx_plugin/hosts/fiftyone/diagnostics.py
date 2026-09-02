"""Copyable diagnostics for FiftyOne augmentation operator failures."""

from __future__ import annotations

import base64
import importlib.metadata
import math
import platform
from collections.abc import Mapping, Sequence
from typing import Any, Final

import albumentationsx_plugin
from albumentationsx_plugin.core import JSONDict, JSONValue
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import ANNOTATION_FIELD_PARAM_PREFIX

DEBUG_BUNDLE_FIELD_NAME: Final[str] = "debug_bundle_json"
DEBUG_BUNDLE_SCHEMA_VERSION: Final[int] = 1
_MAX_SELECTED_SAMPLE_IDS: Final[int] = 20


def build_augmentation_debug_bundle(
    *,
    ctx: Any | None,
    params: Mapping[str, object],
    errors: Sequence[Mapping[str, object]],
    source_scope: str = "",
    pipeline_config: object | None = None,
    selected_sample_ids: Sequence[str] = (),
    exception: BaseException | None = None,
    dry_run: bool = False,
    preview_only: bool = False,
) -> JSONDict:
    """Return a safe JSON payload users can copy into bug reports.

    The bundle intentionally excludes image data and file contents. It keeps
    enough operator context to distinguish expected validation failures from
    plugin bugs without requiring maintainers to read a raw traceback first.
    """

    dependency_versions = _dependency_versions()
    payload: dict[str, object] = {
        "schema_version": DEBUG_BUNDLE_SCHEMA_VERSION,
        "kind": "albumentationsx_augmentation_failure_debug_bundle",
        "summary": _summary(errors),
        "redaction_note": "This bundle does not include image data or file contents.",
        "errors": [_safe_json_object(error) for error in errors],
        "exception": _exception_summary(exception),
        "pipeline_config": _safe_json_value(pipeline_config),
        "operator_params": _safe_json_value(dict(params)),
        "selected_annotation_fields": list(_selected_annotation_fields(params)),
        "execution": _execution_summary(
            source_scope=source_scope,
            selected_sample_ids=selected_sample_ids,
            dry_run=dry_run,
            preview_only=preview_only,
        ),
        "dataset": _dataset_summary(ctx),
        "dependency_versions": dependency_versions,
        "capability_version_key": _capability_version_key(dependency_versions),
        "suggested_next_steps": _suggested_next_steps(errors),
    }
    return _safe_json_object(payload)


def _summary(errors: Sequence[Mapping[str, object]]) -> str:
    if not errors:
        return "Augmentation failed without structured plugin errors."
    first_error = errors[0]
    message = first_error.get("message")
    if isinstance(message, str) and message.strip():
        return message
    code = first_error.get("code")
    return f"Augmentation failed with error code {code}." if isinstance(code, str) else "Augmentation failed."


def _exception_summary(exception: BaseException | None) -> JSONDict:
    if exception is None:
        return {"type": "", "message": ""}
    return {"type": type(exception).__name__, "message": str(exception)}


def _execution_summary(
    *,
    source_scope: str,
    selected_sample_ids: Sequence[str],
    dry_run: bool,
    preview_only: bool,
) -> JSONDict:
    selected_ids = tuple(str(sample_id) for sample_id in selected_sample_ids)
    preview_ids = selected_ids[:_MAX_SELECTED_SAMPLE_IDS]
    return _safe_json_object(
        {
            "source_scope": source_scope,
            "dry_run": dry_run,
            "preview_only": preview_only,
            "selected_sample_count": len(selected_ids),
            "selected_sample_ids": list(preview_ids),
            "selected_sample_ids_truncated": len(selected_ids) > len(preview_ids),
        }
    )


def _dataset_summary(ctx: Any | None) -> JSONDict:
    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    view = getattr(ctx, "view", None) if ctx is not None else None
    if dataset is None:
        return _safe_json_object(
            {
                "available": False,
                "name": "",
                "media_type": "",
                "view_available": view is not None,
                "view_type": type(view).__name__ if view is not None else "",
            }
        )
    return _safe_json_object(
        {
            "available": True,
            "name": str(getattr(dataset, "name", "")),
            "media_type": str(getattr(dataset, "media_type", "")),
            "view_available": view is not None,
            "view_type": type(view).__name__ if view is not None else "",
        }
    )


def _selected_annotation_fields(params: Mapping[str, object]) -> tuple[str, ...]:
    names: list[str] = []
    for key, value in _flatten_annotation_params(params).items():
        if value is not True:
            continue
        names.append(_decode_annotation_field_name(key))
    return tuple(sorted(name for name in names if name))


def _flatten_annotation_params(params: Mapping[str, object]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in params.items():
        if key.startswith(ANNOTATION_FIELD_PARAM_PREFIX):
            flattened[key] = value
        if isinstance(value, Mapping):
            flattened.update(_flatten_annotation_params(value))
    return flattened


def _decode_annotation_field_name(param_name: str) -> str:
    encoded = param_name.removeprefix(ANNOTATION_FIELD_PARAM_PREFIX)
    if not encoded:
        return ""
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(f"{encoded}{padding}").decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return param_name


def _dependency_versions() -> JSONDict:
    return {
        "plugin": albumentationsx_plugin.__version__,
        "python": platform.python_version(),
        "fiftyone": _dependency_version("fiftyone"),
        "albumentationsx": _dependency_version("albumentationsx"),
        "albu-spec": _dependency_version("albu-spec"),
    }


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _capability_version_key(dependency_versions: Mapping[str, object]) -> str:
    albumentationsx_version = dependency_versions.get("albumentationsx", "0+unknown")
    albu_spec_version = dependency_versions.get("albu-spec", "0+unknown")
    return f"albumentationsx-{albumentationsx_version}__albu-spec-{albu_spec_version}"


def _suggested_next_steps(errors: Sequence[Mapping[str, object]]) -> list[str]:
    steps: list[str] = []
    codes = {str(error.get("code", "")) for error in errors}
    reasons = {
        str(context.get("reason", "")) for error in errors if isinstance((context := error.get("context")), Mapping)
    }
    if "missing_runtime_dependency" in codes:
        steps.append("Install plugin requirements in the same Python environment that launches FiftyOne.")
    if "annotation_target_incompatible" in reasons:
        steps.append("Check selected annotation fields and use a pipeline compatible with their target types.")
    if "no_selected_samples" in codes:
        steps.append("Select one or more samples, or switch execution scope to Current view or Entire dataset.")
    if "invalid_execution_scope" in codes:
        steps.append("Choose one of the supported execution scopes in the augmentation form.")
    if "unexpected_runtime_error" in codes:
        steps.append("Copy this debug bundle into the GitHub issue together with the visible traceback.")
    if not steps:
        steps.append("Copy this debug bundle into the GitHub issue together with the visible traceback.")
    return steps


def _safe_json_object(value: Mapping[str, object]) -> JSONDict:
    normalized = _safe_json_value(value)
    return normalized if isinstance(normalized, dict) else {}


def _safe_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(nested_value) for key, nested_value in value.items()}
    if isinstance(value, list | tuple | set):
        return [_safe_json_value(nested_value) for nested_value in value]
    return str(value)
