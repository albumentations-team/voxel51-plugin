"""Executable augmentation operator for catalog-backed FiftyOne forms."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.hosts.fiftyone.dependencies import (
    is_known_runtime_dependency,
    runtime_dependency_package_name,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_execution_scope,
    selected_sample_ids_from_context,
    source_selected_sample_ids,
    source_view_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_stage_parameter_groups
from albumentationsx_plugin.hosts.fiftyone.presets import (
    params_with_previous_run_preset,
    selected_previous_run_key,
    storage_root_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON,
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
        outputs.bool(PREVIEW_ONLY_FIELD_NAME, label="Preview only")
        outputs.str("output_tag", label="Output tag")
        outputs.str("output_dir", label="Output directory")
        outputs.str("manifest_path", label="Manifest path")
        outputs.str("fiftyone_run_key", label="FiftyOne run key")
        outputs.list("errors", types.Object(), label="Errors")
        outputs.int("preview_count", label="Preview results")
        if _preview_only_from_ctx(ctx):
            _render_preview_output_fields(outputs)
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        disabled = not selected_sample_ids and not _has_image_dataset_context(ctx)
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
        preview_only = _preview_only_param(params)
        try:
            source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        except ValueError as error:
            return _invalid_execution_scope_result(params, error)
        if preview_only and not selected_sample_ids:
            return _preview_requires_selected_samples_result(params)
        if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES and not selected_sample_ids:
            return _no_selected_samples_result(params, source_scope=source_scope)
        storage_root = storage_root_from_params(params)
        try:
            execution_params = params_with_previous_run_preset(ctx.dataset, params, storage_root=storage_root)
        except Exception as error:
            return _previous_run_preset_error_result(params, error, source_scope=source_scope)
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
                return _missing_dependency_result(error, source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES)
            return result.to_dict()
        try:
            result = _execute_fixed_augmentation(
                dataset=ctx.dataset,
                view=source_view_from_context(ctx, source_scope),
                selected_sample_ids=source_selected_sample_ids(selected_sample_ids, source_scope),
                params=execution_params,
                storage_root=storage_root,
                progress_reporter=FiftyOneProgressReporter(ctx),
            )
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return _missing_dependency_result(error, source_scope=source_scope)
        _trigger_dataset_reload(ctx, result)
        return result.to_dict()


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
    return flatten_stage_parameter_groups(params) if isinstance(params, Mapping) else {}


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


def _render_preview_json_field(outputs: types.Object, name: str, *, label: str) -> None:
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


def _missing_dependency_result(error: ModuleNotFoundError, *, source_scope: str = "") -> JSONDict:
    return {
        "run_key": "",
        "source_scope": source_scope,
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 1,
        "dry_run": False,
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": [
            {
                "code": "missing_runtime_dependency",
                "message": _missing_dependency_message(error),
                "context": {
                    "missing_module": error.name or "",
                    "package": _dependency_package_name(error),
                },
            }
        ],
    }


def _no_selected_samples_result(params: object, *, source_scope: str) -> JSONDict:
    return {
        "run_key": "",
        "source_scope": source_scope,
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 1,
        "dry_run": _dry_run_param(params),
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": [
            {
                "code": NO_SELECTION_ERROR_CODE,
                "message": "Selected samples scope requires one or more selected samples.",
                "context": {
                    "reason": "empty_selection",
                    "source_scope": source_scope,
                },
            }
        ],
    }


def _preview_requires_selected_samples_result(params: object) -> JSONDict:
    return {
        "run_key": "",
        "source_scope": EXECUTION_SCOPE_SELECTED_SAMPLES,
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 1,
        "dry_run": _dry_run_param(params),
        PREVIEW_ONLY_FIELD_NAME: True,
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": [
            {
                "code": PREVIEW_REQUIRES_SELECTION_ERROR_CODE,
                "message": "Preview requires one or more selected source samples.",
                "context": {
                    "reason": "empty_selection",
                    "max_preview_samples": MAX_PREVIEW_SAMPLES,
                },
            }
        ],
        "preview_count": 0,
        "preview_note": "Select one to three source samples before running preview.",
    }


def _invalid_execution_scope_result(params: object, error: Exception) -> JSONDict:
    return {
        "run_key": "",
        "source_scope": "",
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 1,
        "dry_run": _dry_run_param(params),
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": [
            {
                "code": "invalid_execution_scope",
                "message": "Choose a valid execution scope before running augmentation.",
                "context": {"error_type": type(error).__name__},
            }
        ],
    }


def _previous_run_preset_error_result(params: object, error: Exception, *, source_scope: str = "") -> JSONDict:
    return {
        "run_key": "",
        "source_scope": source_scope,
        "processed_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 1,
        "dry_run": _dry_run_param(params),
        "output_tag": "",
        "output_dir": "",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "errors": [
            {
                "code": "previous_run_preset_unavailable",
                "message": "Previous run settings could not be loaded; choose another run key or clear the field.",
                "context": {
                    "previous_run_key": selected_previous_run_key(params) if isinstance(params, dict) else "",
                    "source_scope": source_scope,
                    "error_type": type(error).__name__,
                },
            }
        ],
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


def _preview_only_from_ctx(ctx: Any | None) -> bool:
    return _preview_only_param(_ctx_params(ctx))


def _trigger_dataset_reload(ctx: Any, result: Any) -> None:
    if getattr(result, "dry_run", False) or getattr(result, "created_count", 0) < 1:
        return

    trigger = getattr(ctx, "trigger", None)
    if not callable(trigger):
        return
    try:
        trigger("reload_dataset")
    except ValueError:
        return


def _is_missing_runtime_dependency(error: ModuleNotFoundError) -> bool:
    return is_known_runtime_dependency(error)


def _dependency_package_name(error: ModuleNotFoundError) -> str:
    return runtime_dependency_package_name(error)


def _missing_dependency_message(error: ModuleNotFoundError) -> str:
    package_name = _dependency_package_name(error)
    return (
        f"Install the '{package_name}' package in the active FiftyOne Python environment, then reload the FiftyOne App."
    )
