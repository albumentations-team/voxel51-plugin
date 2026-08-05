"""Executable augmentation operator for catalog-backed FiftyOne forms."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_stage_parameter_groups
from albumentationsx_plugin.hosts.fiftyone.presets import (
    params_with_previous_run_preset,
    selected_previous_run_key,
    storage_root_from_params,
)

OPERATOR_NAME = "augment_with_albumentationsx"
OPERATOR_LABEL = "Augment with AlbumentationsX"
NO_SELECTION_ERROR_CODE = "no_selected_samples"
RUNTIME_DEPENDENCY_PACKAGES = {
    "albumentations": "albumentationsx",
    "albu_spec": "albu-spec",
}


class AugmentWithAlbumentationsX(foo.Operator):
    """FiftyOne App operator that creates augmented image samples."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Build and apply AlbumentationsX augmentation pipelines to selected samples.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
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
        outputs.int("processed_count", label="Processed")
        outputs.int("created_count", label="Created")
        outputs.int("skipped_count", label="Skipped")
        outputs.int("error_count", label="Errors")
        outputs.bool("dry_run", label="Dry run")
        outputs.str("output_tag", label="Output tag")
        outputs.str("output_dir", label="Output directory")
        outputs.str("manifest_path", label="Manifest path")
        outputs.str("fiftyone_run_key", label="FiftyOne run key")
        outputs.list("errors", types.Object(), label="Errors")
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        selected_sample_ids = _selected_sample_ids(ctx)
        disabled = not selected_sample_ids
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(
                label=OPERATOR_LABEL,
                prompt=True,
                disabled=disabled,
                title="Select samples to augment." if disabled else None,
            ),
        )

    def execute(self, ctx: Any) -> JSONDict:
        params = _ctx_params(ctx)
        selected_sample_ids = _selected_sample_ids(ctx)
        if not selected_sample_ids:
            return _no_selected_samples_result(params)
        storage_root = storage_root_from_params(params)
        try:
            execution_params = params_with_previous_run_preset(ctx.dataset, params, storage_root=storage_root)
        except Exception as error:
            return _previous_run_preset_error_result(params, error)
        try:
            result = _execute_fixed_augmentation(
                dataset=ctx.dataset,
                view=getattr(ctx, "view", None),
                selected_sample_ids=selected_sample_ids,
                params=execution_params,
                storage_root=storage_root,
            )
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return _missing_dependency_result(error)
        _trigger_dataset_reload(ctx, result)
        return result.to_dict()


def _build_dynamic_augment_form(ctx: Any):
    from albumentationsx_plugin.hosts.fiftyone.forms import build_dynamic_augment_form

    return build_dynamic_augment_form(ctx)


def _execute_fixed_augmentation(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation

    return execute_fixed_augmentation(**kwargs)


def _ctx_params(ctx: Any | None) -> dict[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_stage_parameter_groups(params) if isinstance(params, Mapping) else {}


def _missing_dependency_inputs(error: ModuleNotFoundError):
    inputs = types.Object()
    inputs.message(
        "missing_runtime_dependency",
        label="Missing runtime dependency",
        description=_missing_dependency_message(error),
    )
    return inputs


def _missing_dependency_result(error: ModuleNotFoundError) -> JSONDict:
    return {
        "run_key": "",
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


def _no_selected_samples_result(params: object) -> JSONDict:
    return {
        "run_key": "",
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
                "message": "Select one or more samples before running augmentation.",
                "context": {"reason": "empty_selection"},
            }
        ],
    }


def _previous_run_preset_error_result(params: object, error: Exception) -> JSONDict:
    return {
        "run_key": "",
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
                    "error_type": type(error).__name__,
                },
            }
        ],
    }


def _selected_sample_ids(ctx: Any | None) -> tuple[str, ...]:
    selected = getattr(ctx, "selected", ()) if ctx is not None else ()
    return tuple(str(sample_id) for sample_id in (selected or ()))


def _dry_run_param(params: object) -> bool:
    return isinstance(params, dict) and params.get("dry_run") is True


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
    return error.name in RUNTIME_DEPENDENCY_PACKAGES


def _dependency_package_name(error: ModuleNotFoundError) -> str:
    module_name = error.name or ""
    return RUNTIME_DEPENDENCY_PACKAGES.get(module_name, module_name)


def _missing_dependency_message(error: ModuleNotFoundError) -> str:
    package_name = _dependency_package_name(error)
    return (
        f"Install the '{package_name}' package in the active FiftyOne Python environment, then reload the FiftyOne App."
    )
