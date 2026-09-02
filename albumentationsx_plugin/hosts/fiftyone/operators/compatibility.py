"""Read-only FiftyOne operator for dataset augmentation compatibility."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.hosts.fiftyone.dataset_compatibility import (
    build_dataset_compatibility_report,
    dataset_compatibility_error_report,
    missing_dependency_compatibility_report,
)
from albumentationsx_plugin.hosts.fiftyone.dependencies import is_known_runtime_dependency
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CHOICES,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_LABELS,
    default_execution_scope,
    selected_execution_scope,
    selected_sample_ids_from_context,
    source_view_from_context,
)

OPERATOR_NAME = "analyze_albumentationsx_dataset_compatibility"
OPERATOR_LABEL = "Analyze AlbumentationsX Compatibility"


class AnalyzeAlbumentationsXCompatibility(foo.Operator):
    """FiftyOne App operator that reports dataset-specific augmentation safety."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Inspect annotation fields and safe AlbumentationsX target families for the active dataset.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        params = _ctx_params(ctx)
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        selected_scope = _selected_scope_for_form(params, selected_sample_ids=selected_sample_ids)

        inputs = types.Object()
        inputs.enum(
            EXECUTION_SCOPE_FIELD_NAME,
            list(EXECUTION_SCOPE_CHOICES),
            label="Source scope",
            default=selected_scope,
            required=True,
            view=_execution_scope_view(),
        )
        return types.Property(
            inputs,
            view=types.PromptView(
                label=OPERATOR_LABEL,
                submit_button_label="Analyze compatibility",
                cancel_button_label="Close",
            ),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        field_row = types.Object()
        field_row.str("field_name", label="Field")
        field_row.str("label_type", label="Label type")
        field_row.str("support_status", label="Status")
        field_row.str("role", label="Role")
        field_row.str("target", label="Target")
        field_row.int("compatible_transform_count", label="Compatible transforms")
        field_row.str("compatible_transform_examples", label="Examples")
        field_row.str("recommended_filter", label="Recommended filter")
        field_row.str("limitations", label="Limitations")
        field_row.str("message", label="Message")

        target_row = types.Object()
        target_row.str("target", label="Target")
        target_row.str("status", label="Status")
        target_row.int("supported_transform_count", label="Supported transforms")
        target_row.int("excluded_transform_count", label="Excluded transforms")
        target_row.int("image_only_transform_count", label="Image-only transforms")
        target_row.int("geometry_transform_count", label="Geometry transforms")
        target_row.str("example_transforms", label="Examples")
        target_row.str("host_annotation_use", label="FiftyOne use")
        target_row.str("limitations", label="Limitations")

        outputs = types.Object()
        outputs.str("status", label="Status")
        outputs.str("message", label="Message")
        outputs.str("plugin_version", label="Plugin version")
        outputs.str("fiftyone_version", label="FiftyOne version")
        outputs.str("albumentationsx_version", label="AlbumentationsX version")
        outputs.str("albu_spec_version", label="albu-spec version")
        outputs.str("capability_version_key", label="Capability version key")
        outputs.str("dataset_name", label="Dataset")
        outputs.str("media_type", label="Media type")
        outputs.str("source_scope", label="Source scope")
        outputs.str("source_scope_label", label="Source scope label")
        outputs.int("selected_sample_count", label="Selected samples")
        outputs.int("source_count", label="Source samples")
        outputs.bool("source_count_available", label="Source count available")
        outputs.bool("metadata_available", label="Schema metadata available")
        outputs.str("schema_warning", label="Schema warning")
        outputs.int("detected_field_count", label="Detected label fields")
        outputs.int("supported_field_count", label="Supported label fields")
        outputs.int("unsupported_field_count", label="Unsupported label fields")
        outputs.int("copied_field_count", label="Copied fields")
        outputs.int("transformable_field_count", label="Transformable fields")
        outputs.int("total_transform_count", label="Total transforms")
        outputs.int("executable_transform_count", label="Executable transforms")
        outputs.int("excluded_transform_count", label="Excluded transforms")
        _render_json_output_field(outputs, "status_counts_json", label="Status counts")
        outputs.list("annotation_fields", field_row, label="Annotation fields")
        _render_json_output_field(outputs, "annotation_fields_json", label="Annotation fields JSON")
        outputs.list("target_families", target_row, label="Target families")
        _render_json_output_field(outputs, "target_families_json", label="Target families JSON")
        outputs.str("recommendations_text", label="Recommendations")
        _render_json_output_field(outputs, "recommendations_json", label="Recommendations JSON")
        _render_json_output_field(outputs, "report_json", label="Compatibility report JSON")
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
                title="Open an image dataset before analyzing compatibility." if disabled else None,
            ),
        )

    def execute(self, ctx: Any) -> JSONDict:
        params = _ctx_params(ctx)
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        try:
            source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        except ValueError:
            return dataset_compatibility_error_report(
                "Choose a valid source scope before analyzing dataset compatibility.",
                selected_sample_ids=selected_sample_ids,
            )
        try:
            report = build_dataset_compatibility_report(
                dataset=getattr(ctx, "dataset", None),
                view=source_view_from_context(ctx, source_scope),
                selected_sample_ids=selected_sample_ids,
                source_scope=source_scope,
            )
        except ModuleNotFoundError as error:
            if not is_known_runtime_dependency(error):
                raise
            return missing_dependency_compatibility_report(error, source_scope=source_scope)
        return report.to_dict()


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


def _selected_scope_for_form(
    params: Mapping[str, object],
    *,
    selected_sample_ids: tuple[str, ...],
) -> str:
    try:
        return selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    except ValueError:
        return default_execution_scope(selected_sample_ids)


def _execution_scope_view() -> types.DropdownView:
    view = types.DropdownView()
    for choice in EXECUTION_SCOPE_CHOICES:
        view.add_choice(choice, label=EXECUTION_SCOPE_LABELS[choice])
    return view


def _has_image_dataset_context(ctx: Any | None) -> bool:
    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    return dataset is not None and getattr(dataset, "media_type", "image") == "image"


def _render_json_output_field(outputs: types.Object, name: str, *, label: str) -> None:
    outputs.str(
        name,
        label=label,
        view=types.CodeView(language="json", read_only=True),
    )
