"""Build recoverable augmentation errors and diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import fiftyone.operators.types as types

from albumentationsx_plugin.core import JSONDict, PluginError
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    AugmentValidationIssue,
    validation_issues_to_errors,
)
from albumentationsx_plugin.hosts.fiftyone.diagnostics import (
    DEBUG_BUNDLE_FIELD_NAME,
    build_augmentation_debug_bundle,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_sample_ids_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment_contract import (
    _LOGGER,
    NO_SELECTION_ERROR_CODE,
    UNEXPECTED_RUNTIME_ERROR_CODE,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment_values import (
    _dependency_package_name,
    _dry_run_param,
    _json_dump,
    _missing_dependency_message,
    _params_dict,
    _preview_only_param,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    selected_pipeline_preset_key,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_ONLY_FIELD_NAME,
    PREVIEW_REQUIRES_SELECTION_ERROR_CODE,
)


def _missing_dependency_inputs(error: ModuleNotFoundError):
    inputs = types.Object()
    inputs.message(
        "missing_runtime_dependency",
        label="Missing runtime dependency",
        description=_missing_dependency_message(error),
    )
    return inputs


def _missing_dependency_result(
    error: ModuleNotFoundError,
    *,
    params: object | None = None,
    source_scope: str = "",
    ctx: Any | None = None,
) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": "missing_runtime_dependency",
            "message": _missing_dependency_message(error),
            "context": {
                "missing_module": error.name or "",
                "package": _dependency_package_name(error),
            },
        }
    ]
    return _error_result(
        {} if params is None else params,
        errors=errors,
        source_scope=source_scope,
        dry_run=False,
        ctx=ctx,
        exception=error,
    )


def _no_selected_samples_result(params: object, *, source_scope: str, ctx: Any | None = None) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": NO_SELECTION_ERROR_CODE,
            "message": "Selected samples scope requires one or more selected samples.",
            "context": {
                "reason": "empty_selection",
                "source_scope": source_scope,
            },
        }
    ]
    return _error_result(params, errors=errors, source_scope=source_scope, ctx=ctx)


def _preview_requires_selected_samples_result(params: object, *, ctx: Any | None = None) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": PREVIEW_REQUIRES_SELECTION_ERROR_CODE,
            "message": "Preview requires one or more selected source samples.",
            "context": {
                "reason": "empty_selection",
                "max_preview_samples": MAX_PREVIEW_SAMPLES,
            },
        }
    ]
    return _error_result(
        params,
        errors=errors,
        source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
        preview_only=True,
        ctx=ctx,
        extra={
            "preview_count": 0,
            "preview_note": "Select one to three source samples before running preview.",
        },
    )


def _invalid_execution_scope_result(
    params: object,
    error: Exception,
    *,
    ctx: Any | None = None,
) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": "invalid_execution_scope",
            "message": "Choose a valid execution scope before running augmentation.",
            "context": {"error_type": type(error).__name__},
        }
    ]
    return _error_result(params, errors=errors, ctx=ctx, exception=error)


def _pipeline_preset_error_result(
    params: object,
    error: Exception,
    *,
    source_scope: str = "",
    ctx: Any | None = None,
) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": "pipeline_preset_unavailable",
            "message": f"Pipeline could not be saved: {error}. Check its name, settings, and storage access.",
            "context": {
                **dict(getattr(error, "context", {})),
                "pipeline_preset_key": selected_pipeline_preset_key(params) if isinstance(params, dict) else "",
                "source_scope": source_scope,
                "error_type": type(error).__name__,
            },
        }
    ]
    return _error_result(
        params,
        errors=errors,
        source_scope=source_scope,
        ctx=ctx,
        exception=error,
        extra={
            "preset_key": "",
            "preset_name": "",
            "preset_path": "",
        },
    )


def _plugin_error_result(
    params: object,
    error: PluginError,
    *,
    source_scope: str = "",
    ctx: Any | None = None,
) -> JSONDict:
    errors = [error.to_dict()]
    return _error_result(
        params,
        errors=errors,
        source_scope=source_scope,
        ctx=ctx,
        exception=error,
    )


def _unexpected_runtime_error_result(
    params: object,
    error: Exception,
    *,
    source_scope: str = "",
    ctx: Any | None = None,
    phase: str = "augmentation_execution",
    extra: Mapping[str, object] | None = None,
) -> JSONDict:
    _LOGGER.debug("Unexpected augmentation operator error", exc_info=True)
    errors: list[JSONDict] = [
        {
            "code": UNEXPECTED_RUNTIME_ERROR_CODE,
            "message": "Unexpected augmentation error. Copy the debug bundle into a GitHub issue.",
            "context": {
                "error_type": type(error).__name__,
                "cause": str(error),
                "phase": phase,
                "source_scope": source_scope,
            },
        }
    ]
    return _error_result(
        params,
        errors=errors,
        source_scope=source_scope,
        ctx=ctx,
        exception=error,
        extra=extra,
    )


def _augment_validation_error_result(
    params: object,
    issues: tuple[AugmentValidationIssue, ...],
    *,
    source_scope: str = "",
    ctx: Any | None = None,
) -> JSONDict:
    return _error_result(
        params,
        errors=validation_issues_to_errors(issues),
        source_scope=source_scope,
        ctx=ctx,
    )


def _error_result(
    params: object,
    *,
    errors: list[JSONDict],
    source_scope: str = "",
    dry_run: bool | None = None,
    preview_only: bool | None = None,
    extra: Mapping[str, object] | None = None,
    ctx: Any | None = None,
    selected_sample_ids: Sequence[str] | None = None,
    exception: BaseException | None = None,
) -> JSONDict:
    dry_run_value = _dry_run_param(params) if dry_run is None else dry_run
    preview_only_value = _preview_only_param(params) if preview_only is None else preview_only
    diagnostic_selected_sample_ids = (
        selected_sample_ids_from_context(ctx) if selected_sample_ids is None else selected_sample_ids
    )
    payload: dict[str, object] = {
        "run_key": "",
        "source_scope": source_scope,
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": len(errors),
        "dry_run": dry_run_value,
        "execution_status": "cancelled"
        if any(error.get("code") == "augmentation_cancelled" for error in errors)
        else "failed",
        PREVIEW_ONLY_FIELD_NAME: preview_only_value,
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": errors,
        "preview_count": 0,
        **_diagnostic_fields(
            params,
            errors,
            source_scope=source_scope,
            ctx=ctx,
            selected_sample_ids=diagnostic_selected_sample_ids,
            exception=exception,
            dry_run=dry_run_value,
            preview_only=preview_only_value,
        ),
    }
    if extra is not None:
        payload.update(extra)
    return cast(
        JSONDict,
        payload,
    )


def _diagnostic_fields(
    params: object,
    errors: list[JSONDict],
    *,
    source_scope: str = "",
    ctx: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    exception: BaseException | None = None,
    dry_run: bool = False,
    preview_only: bool = False,
) -> JSONDict:
    pipeline_config = _pipeline_config_payload(params)
    operator_params = _params_dict(params)
    return {
        "errors_json": _json_dump(errors),
        "pipeline_config_json": _json_dump(pipeline_config),
        "operator_params_json": _json_dump(operator_params),
        DEBUG_BUNDLE_FIELD_NAME: _json_dump(
            build_augmentation_debug_bundle(
                ctx=ctx,
                params=operator_params,
                errors=errors,
                source_scope=source_scope,
                pipeline_config=pipeline_config,
                selected_sample_ids=selected_sample_ids,
                exception=exception,
                dry_run=dry_run,
                preview_only=preview_only,
            )
        ),
    }


def _pipeline_config_payload(params: object) -> object:
    if not isinstance(params, Mapping):
        return {"status": "unavailable", "reason": "operator_params_unavailable"}
    try:
        config = _build_fixed_pipeline_config(params)
    except Exception as error:
        return {
            "status": "unavailable",
            "error_type": type(error).__name__,
            "message": str(error),
        }
    return config.to_dict()


def _build_fixed_pipeline_config(params: Mapping[str, object]):
    from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import build_fixed_pipeline_config

    return build_fixed_pipeline_config(params)
