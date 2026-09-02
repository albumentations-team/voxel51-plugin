"""Executable augmentation operator for catalog-backed FiftyOne forms."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any, cast

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict, PluginError
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    AugmentValidationIssue,
    validate_augment_template_sources,
    validate_effective_augment_params,
    validation_issues_to_errors,
)
from albumentationsx_plugin.hosts.fiftyone.cancellation import FiftyOneCancellationChecker
from albumentationsx_plugin.hosts.fiftyone.dependencies import (
    is_known_runtime_dependency,
    runtime_dependency_package_name,
)
from albumentationsx_plugin.hosts.fiftyone.diagnostics import (
    DEBUG_BUNDLE_FIELD_NAME,
    build_augmentation_debug_bundle,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_execution_scope,
    selected_sample_ids_from_context,
    source_selected_sample_ids,
    source_view_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_fiftyone_form_groups
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_ONLY_FIELD_NAME,
    params_with_pipeline_preset,
    pipeline_preset_save_requested,
    save_pipeline_preset_from_params,
    selected_pipeline_preset_key,
)
from albumentationsx_plugin.hosts.fiftyone.presets import (
    params_with_previous_run_preset,
    selected_previous_run_key,
    storage_root_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON,
    PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON,
    PREVIEW_FIELD_COMPARISON_IMAGE,
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
from albumentationsx_plugin.hosts.fiftyone.progress import FiftyOneProgressReporter

OPERATOR_NAME = "augment_with_albumentationsx"
OPERATOR_LABEL = "Augment with AlbumentationsX"
NO_SELECTION_ERROR_CODE = "no_selected_samples"
UNEXPECTED_RUNTIME_ERROR_CODE = "unexpected_runtime_error"
_LOGGER = logging.getLogger(__name__)


class AugmentWithAlbumentationsX(foo.Operator):
    """FiftyOne App operator that creates augmented image samples."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Build and apply AlbumentationsX augmentation pipelines to samples, views, or datasets.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=True,
            default_choice_to_delegated=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        try:
            inputs = _build_dynamic_augment_form(ctx)
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            inputs = _missing_dependency_inputs(error)
        return types.Property(
            inputs,
            view=types.PromptView(
                label=OPERATOR_LABEL,
                submit_button_label="Run augmentation",
                cancel_button_label="Close",
            ),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        outputs = types.Object()
        outputs.str("run_key", label="Run key")
        outputs.str("source_scope", label="Source scope")
        outputs.int("processed_count", label="Processed")
        outputs.int("created_count", label="Created")
        outputs.int("skipped_count", label="Skipped")
        outputs.int("error_count", label="Errors")
        outputs.bool("dry_run", label="Dry run")
        outputs.str("execution_status", label="Execution status")
        outputs.bool(PREVIEW_ONLY_FIELD_NAME, label="Preview only")
        outputs.str("output_tag", label="Output tag")
        outputs.str("output_dir", label="Output directory")
        outputs.str("manifest_path", label="Manifest path")
        outputs.str("fiftyone_run_key", label="FiftyOne run key")
        outputs.list("errors", types.Object(), label="Errors")
        _render_json_output_field(outputs, "errors_json", label="Errors JSON")
        _render_json_output_field(outputs, "pipeline_config_json", label="Pipeline config")
        _render_json_output_field(outputs, "operator_params_json", label="Operator params")
        _render_json_output_field(outputs, DEBUG_BUNDLE_FIELD_NAME, label="Debug bundle")
        outputs.int("preview_count", label="Preview results")
        outputs.str("preset_key", label="Preset key")
        outputs.str("preset_name", label="Preset name")
        outputs.str("preset_path", label="Preset path")
        if _preview_only_from_ctx(ctx):
            _render_preview_output_fields(outputs)
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        disabled = not _has_image_dataset_context(ctx)
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(
                label=OPERATOR_LABEL,
                prompt=True,
                disabled=disabled,
                title="Open an image dataset before running augmentation." if disabled else None,
            ),
        )

    def execute(self, ctx: Any) -> JSONDict:
        params = _ctx_params(ctx)
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        storage_root = storage_root_from_params(params)
        template_source_issues = validate_augment_template_sources(params)
        if template_source_issues:
            return _augment_validation_error_result(
                params,
                template_source_issues,
                ctx=ctx,
            )
        if _save_preset_only_param(params):
            try:
                preset_params = params_with_pipeline_preset(params, storage_root=storage_root)
                preset_params = params_with_previous_run_preset(ctx.dataset, preset_params, storage_root=storage_root)
                validation_issues = validate_effective_augment_params(preset_params)
                if validation_issues:
                    return _augment_validation_error_result(
                        preset_params,
                        validation_issues,
                        ctx=ctx,
                    )
                return save_pipeline_preset_from_params(preset_params, storage_root=storage_root).to_dict()
            except Exception as error:
                return _pipeline_preset_error_result(params, error, ctx=ctx)
        preview_only = _preview_only_param(params)
        try:
            source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        except ValueError as error:
            return _invalid_execution_scope_result(params, error, ctx=ctx)
        if preview_only and not selected_sample_ids:
            return _preview_requires_selected_samples_result(params, ctx=ctx)
        if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES and not selected_sample_ids:
            return _no_selected_samples_result(params, source_scope=source_scope, ctx=ctx)
        try:
            execution_params = params_with_pipeline_preset(params, storage_root=storage_root)
        except Exception as error:
            return _pipeline_preset_error_result(
                params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        try:
            execution_params = params_with_previous_run_preset(ctx.dataset, execution_params, storage_root=storage_root)
        except Exception as error:
            return _previous_run_preset_error_result(
                params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        validation_issues = validate_effective_augment_params(execution_params)
        if validation_issues:
            return _augment_validation_error_result(
                execution_params,
                validation_issues,
                source_scope=source_scope,
                ctx=ctx,
            )
        execution_params[EXECUTION_SCOPE_FIELD_NAME] = source_scope
        if preview_only:
            preview_params = dict(execution_params)
            preview_params[EXECUTION_SCOPE_FIELD_NAME] = EXECUTION_SCOPE_SELECTED_SAMPLES
            preview_params["dry_run"] = False
            try:
                result = _execute_fixed_augmentation_preview(
                    dataset=ctx.dataset,
                    view=source_view_from_context(ctx, EXECUTION_SCOPE_SELECTED_SAMPLES),
                    selected_sample_ids=selected_sample_ids[:MAX_PREVIEW_SAMPLES],
                    params=preview_params,
                )
            except ModuleNotFoundError as error:
                if not _is_missing_runtime_dependency(error):
                    raise
                return _missing_dependency_result(
                    error,
                    params=preview_params,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            except PluginError as error:
                return _plugin_error_result(
                    preview_params,
                    error,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            except Exception as error:
                return _unexpected_runtime_error_result(
                    preview_params,
                    error,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            return result.to_dict()
        saved_preset = None
        if pipeline_preset_save_requested(execution_params) and not _dry_run_param(execution_params):
            try:
                saved_preset = save_pipeline_preset_from_params(execution_params, storage_root=storage_root)
            except Exception as error:
                return _pipeline_preset_error_result(
                    params,
                    error,
                    source_scope=source_scope,
                    ctx=ctx,
                )
        try:
            result = _execute_fixed_augmentation(
                dataset=ctx.dataset,
                view=source_view_from_context(ctx, source_scope),
                selected_sample_ids=source_selected_sample_ids(selected_sample_ids, source_scope),
                params=execution_params,
                storage_root=storage_root,
                cancellation_checker=FiftyOneCancellationChecker(ctx),
                progress_reporter=FiftyOneProgressReporter(ctx),
            )
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return _missing_dependency_result(
                error,
                params=execution_params,
                source_scope=source_scope,
                ctx=ctx,
            )
        except PluginError as error:
            return _plugin_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        except Exception as error:
            return _unexpected_runtime_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        try:
            _trigger_dataset_reload(ctx, result)
        except Exception as error:
            return _unexpected_runtime_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
                phase="dataset_reload",
                extra=_successful_result_output_fields(result),
            )
        output = result.to_dict()
        if saved_preset is not None:
            output.update(_pipeline_preset_output_fields(saved_preset))
        return output


def _build_dynamic_augment_form(ctx: Any):
    from albumentationsx_plugin.hosts.fiftyone.forms import build_dynamic_augment_form

    return build_dynamic_augment_form(ctx)


def _execute_fixed_augmentation(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation

    return execute_fixed_augmentation(**kwargs)


def _execute_fixed_augmentation_preview(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation_preview

    return execute_fixed_augmentation_preview(**kwargs)


def _ctx_params(ctx: Any | None) -> dict[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_fiftyone_form_groups(params) if isinstance(params, Mapping) else {}


def _render_preview_output_fields(outputs: types.Object) -> None:
    outputs.str(
        "preview_note",
        label="Preview note",
        view=types.FieldView(read_only=True),
    )
    for slot_number in range(1, MAX_PREVIEW_SAMPLES + 1):
        label_prefix = f"Preview {slot_number}"
        outputs.str(preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_SAMPLE_ID), label=f"{label_prefix} source ID")
        outputs.str(
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_FILEPATH),
            label=f"{label_prefix} source file",
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_IMAGE),
            types.String(),
            label=f"{label_prefix} source image",
            view=types.ImageView(
                height="240px",
                width="320px",
                alt=f"{label_prefix} source image",
                read_only=True,
            ),
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_OUTPUT_IMAGE),
            types.String(),
            label=f"{label_prefix} augmented image",
            view=types.ImageView(
                height="240px",
                width="320px",
                alt=f"{label_prefix} augmented image",
                read_only=True,
            ),
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_COMPARISON_IMAGE),
            types.String(),
            label=f"{label_prefix} annotated comparison",
            view=types.ImageView(
                height="300px",
                width="640px",
                alt=f"{label_prefix} annotated before and after comparison",
                read_only=True,
            ),
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_REPLAY_JSON),
            label=f"{label_prefix} sampled parameters",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_LABELS_JSON),
            label=f"{label_prefix} transformed labels",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON),
            label=f"{label_prefix} annotation summary",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON),
            label=f"{label_prefix} annotation comparison",
        )


def _render_preview_json_field(outputs: types.Object, name: str, *, label: str) -> None:
    _render_json_output_field(outputs, name, label=label)


def _render_json_output_field(outputs: types.Object, name: str, *, label: str) -> None:
    outputs.str(
        name,
        label=label,
        view=types.CodeView(language="json", read_only=True),
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


def _previous_run_preset_error_result(
    params: object,
    error: Exception,
    *,
    source_scope: str = "",
    ctx: Any | None = None,
) -> JSONDict:
    errors: list[JSONDict] = [
        {
            "code": "previous_run_preset_unavailable",
            "message": "Previous run settings could not be loaded; choose another run key or clear the field.",
            "context": {
                "previous_run_key": selected_previous_run_key(params) if isinstance(params, dict) else "",
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
    )


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
            "message": "Pipeline preset could not be loaded or saved; check the preset name and settings.",
            "context": {
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
        "execution_status": "",
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
    from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config

    return build_fixed_pipeline_config(params)


def _params_dict(params: object) -> dict[str, object]:
    return dict(params) if isinstance(params, Mapping) else {}


def _json_dump(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _pipeline_preset_output_fields(save_result: Any) -> JSONDict:
    preset_result = save_result.to_dict()
    return {
        "preset_key": preset_result["preset_key"],
        "preset_name": preset_result["preset_name"],
        "preset_path": preset_result["preset_path"],
    }


def _successful_result_output_fields(result: Any) -> Mapping[str, object]:
    return {
        "run_key": getattr(result, "run_key", ""),
        "processed_count": getattr(result, "processed_count", 0),
        "created_count": getattr(result, "created_count", 0),
        "skipped_count": getattr(result, "skipped_count", 0),
        "dry_run": getattr(result, "dry_run", False),
        "execution_status": getattr(result, "execution_status", ""),
        "output_tag": getattr(result, "output_tag", ""),
        "output_dir": getattr(result, "output_dir", ""),
        "manifest_path": getattr(result, "manifest_path", ""),
        "fiftyone_run_key": getattr(result, "fiftyone_run_key", ""),
    }


def _has_image_dataset_context(ctx: Any | None) -> bool:
    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    if dataset is None:
        return False
    media_type = getattr(dataset, "media_type", None)
    return media_type in (None, "image")


def _dry_run_param(params: object) -> bool:
    return isinstance(params, dict) and params.get("dry_run") is True


def _preview_only_param(params: object) -> bool:
    return isinstance(params, dict) and params.get(PREVIEW_ONLY_FIELD_NAME) is True


def _save_preset_only_param(params: object) -> bool:
    return isinstance(params, dict) and params.get(SAVE_PRESET_ONLY_FIELD_NAME) is True


def _preview_only_from_ctx(ctx: Any | None) -> bool:
    return _preview_only_param(_ctx_params(ctx))


def _trigger_dataset_reload(ctx: Any, result: Any) -> None:
    if getattr(result, "dry_run", False) or getattr(result, "created_count", 0) < 1:
        return

    trigger = getattr(ctx, "trigger", None)
    if not callable(trigger):
        return
    trigger("reload_dataset")


def _is_missing_runtime_dependency(error: ModuleNotFoundError) -> bool:
    return is_known_runtime_dependency(error)


def _dependency_package_name(error: ModuleNotFoundError) -> str:
    return runtime_dependency_package_name(error)


def _missing_dependency_message(error: ModuleNotFoundError) -> str:
    package_name = _dependency_package_name(error)
    return (
        f"Install the '{package_name}' package in the active FiftyOne Python environment, then reload the FiftyOne App."
    )
