"""Inline compatibility preview for the dynamic augment form."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import fiftyone.operators.types as types

from albumentationsx_plugin.core import PipelineConfig
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ANNOTATION_ROLE_COPIED,
    ANNOTATION_ROLE_TRANSFORMED,
    AnnotationFieldSelection,
    annotation_pipeline_compatibility_conflicts,
    annotation_pipeline_field_roles,
    selected_annotation_fields_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.dataset_compatibility import (
    DatasetCompatibilityReport,
    build_dataset_compatibility_report,
)
from albumentationsx_plugin.hosts.fiftyone.dependencies import (
    is_known_runtime_dependency,
    runtime_dependency_package_name,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import source_view_from_context

INLINE_COMPATIBILITY_SECTION_FIELD_NAME: Final[str] = "_dataset_compatibility"
INLINE_COMPATIBILITY_SUMMARY_FIELD_NAME: Final[str] = "_dataset_compatibility_summary"
INLINE_COMPATIBILITY_WARNING_FIELD_NAME: Final[str] = "_dataset_compatibility_warning"
INLINE_COMPATIBILITY_RECOMMENDATIONS_FIELD_NAME: Final[str] = "_dataset_compatibility_recommendations"
ANNOTATION_COMPATIBILITY_WARNING_LIMIT: Final[int] = 3
_FIELD_PREVIEW_LIMIT: Final[int] = 5
_RECOMMENDATION_LIMIT: Final[int] = 3


@dataclass(frozen=True, slots=True)
class InlineCompatibilityPreview:
    """Compact compatibility payload rendered inside the augment form."""

    summary: str
    warning: str = ""
    recommendations: tuple[str, ...] = ()


def build_inline_compatibility_preview(
    *,
    ctx: Any | None,
    params: Mapping[str, object],
    selected_sample_ids: Sequence[str],
    source_scope: str,
    pipeline: PipelineConfig,
    catalog_provider: Any,
) -> InlineCompatibilityPreview | None:
    """Build a compact dataset/pipeline compatibility preview for the form."""

    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    if dataset is None:
        return None

    try:
        selection = selected_annotation_fields_from_params(params, dataset)
        report = build_dataset_compatibility_report(
            dataset=dataset,
            view=source_view_from_context(ctx, source_scope),
            selected_sample_ids=selected_sample_ids,
            source_scope=source_scope,
            provider=catalog_provider,
            annotation_selection=selection,
        )
    except ModuleNotFoundError as error:
        if not is_known_runtime_dependency(error):
            raise
        return _missing_dependency_preview(error)
    except Exception as error:
        report = build_dataset_compatibility_report(
            dataset=dataset,
            view=source_view_from_context(ctx, source_scope),
            selected_sample_ids=selected_sample_ids,
            source_scope=source_scope,
            provider=catalog_provider,
        )
        return InlineCompatibilityPreview(
            summary=_report_summary(report, selection=None, pipeline=pipeline, catalog_provider=catalog_provider),
            warning=f"Annotation field choices could not be resolved: {type(error).__name__}: {error}",
            recommendations=_visible_recommendations(report),
        )

    conflicts = annotation_pipeline_compatibility_conflicts(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
    )
    warning = annotation_compatibility_warning(conflicts) if conflicts else ""
    return InlineCompatibilityPreview(
        summary=_report_summary(report, selection=selection, pipeline=pipeline, catalog_provider=catalog_provider),
        warning=warning,
        recommendations=_visible_recommendations(report),
    )


def render_inline_compatibility_preview(
    inputs: types.Object,
    preview: InlineCompatibilityPreview | None,
) -> None:
    """Render the compact compatibility preview into a FiftyOne form."""

    if preview is None:
        return

    inputs.view(
        INLINE_COMPATIBILITY_SECTION_FIELD_NAME,
        types.Header(
            label="Compatibility",
            description="A compact preflight view for the current source scope, selected annotations, and pipeline.",
        ),
    )
    inputs.message(
        INLINE_COMPATIBILITY_SUMMARY_FIELD_NAME,
        label="Dataset compatibility",
        description=preview.summary,
    )
    if preview.warning:
        inputs.view(
            INLINE_COMPATIBILITY_WARNING_FIELD_NAME,
            types.Warning(
                label="Compatibility warning",
                description=preview.warning,
            ),
        )
    if preview.recommendations:
        inputs.message(
            INLINE_COMPATIBILITY_RECOMMENDATIONS_FIELD_NAME,
            label="Recommendations",
            description="\n".join(f"- {recommendation}" for recommendation in preview.recommendations),
        )


def annotation_compatibility_warning(conflicts: Sequence[object]) -> str:
    """Return a concise warning for selected field/pipeline conflicts."""

    summaries = tuple(
        _annotation_compatibility_conflict_summary(conflict) for conflict in conflicts if isinstance(conflict, Mapping)
    )
    if not summaries:
        return "Selected annotation fields are not compatible with the active augmentation pipeline."

    visible_summaries = summaries[:ANNOTATION_COMPATIBILITY_WARNING_LIMIT]
    details = "\n".join(f"- {summary}" for summary in visible_summaries)
    omitted_count = len(summaries) - len(visible_summaries)
    omitted = f"\n- {omitted_count} more conflict(s) hidden." if omitted_count > 0 else ""
    return (
        "Selected annotation fields are not compatible with the active augmentation pipeline:\n"
        f"{details}{omitted}\n"
        "Disable the listed annotation fields or remove/replace the incompatible stage before running augmentation. "
        "Open Analyze AlbumentationsX Compatibility for the full dataset report."
    )


def _report_summary(
    report: DatasetCompatibilityReport,
    *,
    selection: AnnotationFieldSelection | None,
    pipeline: PipelineConfig,
    catalog_provider: Any,
) -> str:
    source = report.source
    source_count = str(source.source_count) if source.source_count_available else "unknown number of"
    lines = [
        (
            f"Scope: {source.source_scope_label}; source samples: {source_count}; "
            f"selected samples: {source.selected_sample_count}; "
            f"schema: {'available' if report.metadata_available else 'unavailable'}."
        ),
        (
            f"Annotations: {report.supported_field_count} selected supported field(s), "
            f"{report.transformable_field_count} transform-capable, {report.copied_field_count} copy-only, "
            f"{report.unsupported_field_count} unsupported/excluded."
        ),
        _pipeline_summary(selection, pipeline=pipeline, catalog_provider=catalog_provider),
    ]
    if report.schema_warning:
        lines.append(f"Schema warning: {report.schema_warning}")
    return "\n".join(lines)


def _pipeline_summary(
    selection: AnnotationFieldSelection | None,
    *,
    pipeline: PipelineConfig,
    catalog_provider: Any,
) -> str:
    transform_names = ", ".join(transform.name for transform in pipeline.transforms) or "none"
    if selection is None:
        return f"Pipeline: {transform_names}; annotation field roles are unavailable."
    if not selection.selected_fields:
        return f"Pipeline: {transform_names}; no annotation fields are selected."

    roles = annotation_pipeline_field_roles(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
    )
    transformed = tuple(field.name for field, role in roles if role == ANNOTATION_ROLE_TRANSFORMED)
    copied = tuple(field.name for field, role in roles if role == ANNOTATION_ROLE_COPIED)
    role_parts = []
    if transformed:
        role_parts.append(f"transforms {_field_list(transformed)}")
    if copied:
        role_parts.append(f"copies {_field_list(copied)}")
    role_text = "; ".join(role_parts) if role_parts else "does not touch annotation fields"
    return f"Pipeline: {transform_names}; {role_text}."


def _missing_dependency_preview(error: ModuleNotFoundError) -> InlineCompatibilityPreview:
    package_name = runtime_dependency_package_name(error)
    return InlineCompatibilityPreview(
        summary="Compatibility preview is unavailable because a runtime dependency is missing.",
        warning=(
            f"Install the '{package_name}' package in the active FiftyOne Python environment, "
            "then reload the FiftyOne App."
        ),
    )


def _visible_recommendations(report: DatasetCompatibilityReport) -> tuple[str, ...]:
    return tuple(report.recommendations[:_RECOMMENDATION_LIMIT])


def _field_list(field_names: Sequence[str]) -> str:
    visible = tuple(field_names[:_FIELD_PREVIEW_LIMIT])
    text = ", ".join(f"`{field_name}`" for field_name in visible)
    hidden_count = len(field_names) - len(visible)
    if hidden_count > 0:
        text = f"{text}, and {hidden_count} more"
    return text


def _annotation_compatibility_conflict_summary(conflict: Mapping[str, object]) -> str:
    field_name = _mapping_string(conflict, "field_name", default="selected field")
    label_type = _mapping_string(conflict, "label_type", default="unknown")
    target = _mapping_string(conflict, "target", default="unknown")
    transform_name = _mapping_string(conflict, "transform_name", default="selected transform")
    stage_number = conflict.get("stage_number")
    stage_label = f" at stage {stage_number}" if stage_number is not None else ""
    message = _mapping_string(conflict, "message", default="")
    reason = _mapping_string(conflict, "reason", default="")

    summary = (
        f"`{field_name}` ({label_type}) requires target `{target}`, "
        f"but `{transform_name}`{stage_label} cannot transform it safely."
    )
    if message:
        return f"{summary} {message}"
    if reason:
        return f"{summary} Reason: {reason}."
    return summary


def _mapping_string(value: Mapping[str, object], key: str, *, default: str) -> str:
    raw_value = value.get(key)
    return raw_value if isinstance(raw_value, str) and raw_value else default
