"""Executable augmentation operator for catalog-backed FiftyOne forms."""

from __future__ import annotations

from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict

OPERATOR_NAME = "augment_with_albumentationsx"
OPERATOR_LABEL = "Augment with AlbumentationsX"
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
            description="Build and preview AlbumentationsX augmentation pipelines.",
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
            view=types.View(label=OPERATOR_LABEL),
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
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(label=OPERATOR_LABEL, prompt=True),
        )

    def execute(self, ctx: Any) -> JSONDict:
        params = getattr(ctx, "params", {}) or {}
        selected = getattr(ctx, "selected", ()) or ()
        try:
            result = _execute_fixed_augmentation(
                dataset=ctx.dataset,
                view=getattr(ctx, "view", None),
                selected_sample_ids=tuple(str(sample_id) for sample_id in selected),
                params=params,
            )
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return _missing_dependency_result(error)
        return result.to_dict()


def _build_dynamic_augment_form(ctx: Any):
    from albumentationsx_plugin.hosts.fiftyone.forms import build_dynamic_augment_form

    return build_dynamic_augment_form(ctx)


def _execute_fixed_augmentation(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation

    return execute_fixed_augmentation(**kwargs)


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
