"""Read-only FiftyOne operator for inspecting persisted augmentation runs."""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.hosts.fiftyone.run_summary import build_run_summary, list_available_run_keys

OPERATOR_NAME = "view_albumentationsx_run"
OPERATOR_LABEL = "View AlbumentationsX Run"
RUN_KEY_FIELD_NAME = "run_key"
STORAGE_ROOT_PARAM_NAME = "_storage_root"


class ViewAlbumentationsXRun(foo.Operator):
    """FiftyOne App operator that reports manifest-backed run metadata."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Inspect a persisted AlbumentationsX augmentation run.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        params = _ctx_params(ctx)
        storage_root = _storage_root(params)
        dataset = getattr(ctx, "dataset", None)
        run_keys = list_available_run_keys(dataset, storage_root=storage_root) if dataset is not None else ()

        inputs = types.Object()
        if run_keys:
            choices = types.AutocompleteView(label="Run key", allow_user_input=False)
            for run_key in run_keys:
                choices.add_choice(run_key, label=run_key)
            inputs.enum(
                RUN_KEY_FIELD_NAME,
                run_keys,
                label="Run key",
                default=_selected_run_key(params.get(RUN_KEY_FIELD_NAME), run_keys),
                required=True,
                view=choices,
            )
        else:
            inputs.str(
                RUN_KEY_FIELD_NAME,
                label="Run key",
                description="No persisted AlbumentationsX runs were found for this dataset.",
            )

        return types.Property(
            inputs,
            view=types.View(label=OPERATOR_LABEL),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        outputs = types.Object()
        outputs.str("run_key", label="Run key")
        outputs.str("status", label="Status")
        outputs.str("message", label="Message")
        outputs.str("manifest_path", label="Manifest path")
        outputs.str("fiftyone_run_key", label="FiftyOne run key")
        outputs.str("cleanup_status", label="Cleanup status")
        outputs.str("cleaned_at", label="Cleaned at")
        outputs.str("run_label", label="Run label")
        outputs.str("run_label_slug", label="Run label slug")
        outputs.int("source_count", label="Sources")
        outputs.int("created_count", label="Created samples")
        outputs.int("output_count", label="Manifest outputs")
        outputs.int("available_output_count", label="Available outputs")
        outputs.int("missing_output_count", label="Missing outputs")
        outputs.int("error_count", label="Errors")
        outputs.int("replay_count", label="Replay records")
        outputs.bool("replay_available", label="Replay available")
        outputs.str("output_tag", label="Output tag")
        outputs.str("output_dir", label="Output directory")
        outputs.str("plugin_version", label="Plugin version")
        outputs.str("dependency_versions_json", label="Dependency versions")
        outputs.str("pipeline_summary", label="Transform summary")
        outputs.str("pipeline_config_json", label="Transform config")
        outputs.str("errors_json", label="Errors")
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        disabled = not _has_available_runs(ctx)
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(
                label=OPERATOR_LABEL,
                prompt=True,
                disabled=disabled,
                title="Create an AlbumentationsX run before inspecting it." if disabled else None,
            ),
        )

    def execute(self, ctx: Any) -> JSONDict:
        params = _ctx_params(ctx)
        summary = build_run_summary(
            ctx.dataset,
            _selected_run_key(params.get(RUN_KEY_FIELD_NAME), ()),
            storage_root=_storage_root(params),
        )
        return summary.to_dict()


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


def _selected_run_key(raw_value: object, run_keys: tuple[str, ...]) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value
    return run_keys[0] if run_keys else ""


def _has_available_runs(ctx: Any | None) -> bool:
    if ctx is None:
        return False
    dataset = getattr(ctx, "dataset", None)
    if dataset is None:
        return False
    try:
        return bool(list_available_run_keys(dataset, storage_root=_storage_root(_ctx_params(ctx))))
    except Exception:
        return False


def _storage_root(params: Mapping[str, object]) -> str | PathLike[str] | None:
    value = params.get(STORAGE_ROOT_PARAM_NAME)
    if isinstance(value, str):
        return value
    return value if isinstance(value, PathLike) else None
