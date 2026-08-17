"""Read-only FiftyOne operator for browsing transform capability metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import CapabilityStatus, JSONDict
from albumentationsx_plugin.hosts.fiftyone.capabilities import (
    ALL_FILTER_VALUE,
    CapabilityBrowserFilters,
    build_capability_browser_result,
    build_capability_filter_choices,
    missing_dependency_browser_result,
)

OPERATOR_NAME = "show_albumentationsx_capabilities"
OPERATOR_LABEL = "Show AlbumentationsX Capabilities"
RUNTIME_DEPENDENCY_PACKAGES = {
    "albumentations": "albumentationsx",
    "albu_spec": "albu-spec",
}


class ShowAlbumentationsXCapabilities(foo.Operator):
    """FiftyOne App operator that shows the current transform catalog contract."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Inspect supported AlbumentationsX transforms, target compatibility, and exclusion reasons.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        try:
            status_choices, target_choices = build_capability_filter_choices()
            inputs = _filter_inputs(_ctx_params(ctx), status_choices=status_choices, target_choices=target_choices)
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            inputs = _missing_dependency_inputs(error)
        return types.Property(
            inputs,
            view=types.PromptView(
                label=OPERATOR_LABEL,
                submit_button_label="Show capabilities",
                cancel_button_label="Close",
            ),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        row = types.Object()
        row.str("name", label="Transform")
        row.str("status", label="Status")
        row.str("targets", label="Targets")
        row.str("reason_code", label="Reason code")
        row.str("message", label="Reason")
        row.str("advanced_parameter_status", label="Advanced parameters")
        row.str("advanced_parameters", label="Advanced parameter names")
        row.int("parameter_count", label="Parameters")
        row.str("transform_type", label="Transform type")
        row.str("module", label="Module")
        row.str("docstring_short", label="Description")

        outputs = types.Object()
        outputs.str("status", label="Status")
        outputs.str("message", label="Message")
        outputs.str("plugin_version", label="Plugin version")
        outputs.str("fiftyone_version", label="FiftyOne version")
        outputs.str("albumentationsx_version", label="AlbumentationsX version")
        outputs.str("albu_spec_version", label="albu-spec version")
        outputs.str("capability_version_key", label="Capability version key")
        outputs.str("query", label="Search")
        outputs.str("status_filter", label="Status filter")
        outputs.str("target_filter", label="Target filter")
        outputs.int("total_count", label="Total transforms")
        outputs.int("matching_count", label="Matching transforms")
        outputs.int("supported_count", label="Supported choices")
        outputs.int("excluded_count", label="Excluded transforms")
        outputs.str("status_counts_json", label="Status counts")
        outputs.str("matching_status_counts_json", label="Matching status counts")
        outputs.list("transforms", row, label="Transforms")
        outputs.str("transforms_json", label="Transforms JSON")
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(
                label=OPERATOR_LABEL,
                prompt=True,
            ),
        )

    def execute(self, ctx: Any) -> JSONDict:
        try:
            result = build_capability_browser_result(CapabilityBrowserFilters.from_params(_ctx_params(ctx)))
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return missing_dependency_browser_result(error)
        return result.to_dict()


def _filter_inputs(
    params: Mapping[str, object],
    *,
    status_choices: tuple[str, ...],
    target_choices: tuple[str, ...],
) -> types.Object:
    inputs = types.Object()
    inputs.str(
        "query",
        label="Search",
        default=_string_param(params.get("query")),
        required=False,
        allow_empty=True,
        view=types.FieldView(caption="Filter by transform name."),
    )
    inputs.enum(
        "status_filter",
        list(status_choices),
        label="Capability status",
        default=_selected_filter(params.get("status_filter"), status_choices),
        required=True,
        view=_dropdown_view(status_choices),
    )
    inputs.enum(
        "target_filter",
        list(target_choices),
        label="Target",
        default=_selected_filter(params.get("target_filter"), target_choices),
        required=True,
        view=_dropdown_view(target_choices),
    )
    return inputs


def _missing_dependency_inputs(error: ModuleNotFoundError) -> types.Object:
    payload = missing_dependency_browser_result(error)
    inputs = types.Object()
    inputs.message(
        "missing_runtime_dependency",
        label="Missing runtime dependency",
        description=str(payload["message"]),
    )
    return inputs


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


def _selected_filter(raw_value: object, choices: tuple[str, ...]) -> str:
    value = _string_param(raw_value)
    return value if value in choices else ALL_FILTER_VALUE


def _dropdown_view(choices: tuple[str, ...]) -> types.DropdownView:
    view = types.DropdownView()
    for choice in choices:
        view.add_choice(choice, label=_choice_label(choice))
    return view


def _choice_label(choice: str) -> str:
    if choice == ALL_FILTER_VALUE:
        return "All"
    if choice in {status.value for status in CapabilityStatus}:
        return choice.replace("_", " ").capitalize()
    return choice


def _string_param(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_missing_runtime_dependency(error: ModuleNotFoundError) -> bool:
    return error.name in RUNTIME_DEPENDENCY_PACKAGES
