"""Shared validation for FiftyOne augmentation form and execution params."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    JSONDict,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_NAME_FIELD_NAME,
    SAVE_PRESET_ONLY_FIELD_NAME,
    pipeline_preset_save_requested,
    selected_pipeline_preset_key,
)
from albumentationsx_plugin.hosts.fiftyone.presets import (
    selected_previous_run_key,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import PREVIEW_ONLY_FIELD_NAME

DRY_RUN_FIELD_NAME: Final[str] = "dry_run"
PRESET_SOURCE_CONFLICT_CODE: Final[str] = "preset_source_conflict"
DUPLICATE_STAGE_ORDER_CODE: Final[str] = "duplicate_pipeline_stage_order"
INVALID_EXECUTION_MODE_CODE: Final[str] = "invalid_execution_mode"
VALIDATION_WARNING_LIMIT: Final[int] = 4


@dataclass(frozen=True, slots=True)
class AugmentValidationIssue:
    """One user-facing augment configuration validation issue."""

    code: str
    message: str
    context: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Serialize this issue for operator outputs."""

        return normalize_json_mapping(
            {
                "code": self.code,
                "message": self.message,
                "context": normalize_json_mapping(self.context),
            }
        )


def validate_augment_template_sources(params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    """Validate mutually exclusive template sources before applying presets."""

    named_preset_key = selected_pipeline_preset_key(params)
    previous_run_key = selected_previous_run_key(params)
    if not named_preset_key or not previous_run_key:
        return ()

    return (
        AugmentValidationIssue(
            code=PRESET_SOURCE_CONFLICT_CODE,
            message="Choose either a named preset or a previous run, not both.",
            context={
                "reason": "mutually_exclusive_template_sources",
                "pipeline_preset_key": named_preset_key,
                "previous_run_key": previous_run_key,
            },
        ),
    )


def validate_effective_augment_params(params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    """Validate effective params after any selected preset has been applied."""

    return (
        *validate_execution_mode_params(params),
        *validate_pipeline_stage_orders(params),
    )


def validate_execution_mode_params(params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    """Validate execution modes that would otherwise silently override each other."""

    issues: list[AugmentValidationIssue] = []
    preview_only = _bool_param(params, PREVIEW_ONLY_FIELD_NAME, default=False)
    dry_run = _bool_param(params, DRY_RUN_FIELD_NAME, default=False)
    save_preset_only = _bool_param(params, SAVE_PRESET_ONLY_FIELD_NAME, default=False)
    save_preset_requested = pipeline_preset_save_requested(params)

    if preview_only and dry_run:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Choose either Preview only or Dry run, not both.",
                context={
                    "reason": "preview_only_conflicts_with_dry_run",
                    PREVIEW_ONLY_FIELD_NAME: True,
                    DRY_RUN_FIELD_NAME: True,
                },
            )
        )

    if save_preset_only and preview_only:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Save preset only cannot be combined with Preview only.",
                context={
                    "reason": "save_preset_only_conflicts_with_preview_only",
                    SAVE_PRESET_ONLY_FIELD_NAME: True,
                    PREVIEW_ONLY_FIELD_NAME: True,
                },
            )
        )

    if save_preset_only and dry_run:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Save preset only cannot be combined with Dry run.",
                context={
                    "reason": "save_preset_only_conflicts_with_dry_run",
                    SAVE_PRESET_ONLY_FIELD_NAME: True,
                    DRY_RUN_FIELD_NAME: True,
                },
            )
        )

    if save_preset_only and not save_preset_requested:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Preset name is required when Save preset only is enabled.",
                context={
                    "reason": "save_preset_only_requires_preset_name",
                    SAVE_PRESET_ONLY_FIELD_NAME: True,
                    "preset_name_field": SAVE_PRESET_NAME_FIELD_NAME,
                },
            )
        )

    if save_preset_requested and not save_preset_only and preview_only:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Preview only does not save named presets; disable Preview only or enable Save preset only.",
                context={
                    "reason": "preview_only_would_skip_preset_save",
                    PREVIEW_ONLY_FIELD_NAME: True,
                    SAVE_PRESET_NAME_FIELD_NAME: _string_param(params, SAVE_PRESET_NAME_FIELD_NAME),
                },
            )
        )

    if save_preset_requested and not save_preset_only and dry_run:
        issues.append(
            AugmentValidationIssue(
                code=INVALID_EXECUTION_MODE_CODE,
                message="Dry run does not save named presets; disable Dry run or enable Save preset only.",
                context={
                    "reason": "dry_run_would_skip_preset_save",
                    DRY_RUN_FIELD_NAME: True,
                    SAVE_PRESET_NAME_FIELD_NAME: _string_param(params, SAVE_PRESET_NAME_FIELD_NAME),
                },
            )
        )

    return tuple(issues)


def validate_pipeline_stage_orders(params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    """Validate that enabled pipeline stages have unique execution orders."""

    grouped: dict[int, list[int]] = defaultdict(list)
    visible_step_count = _pipeline_step_count(params)
    for step_number in range(1, visible_step_count + 1):
        enabled = _bool_param(params, pipeline_stage_enabled_field_name(step_number), default=True)
        if not enabled:
            continue
        execution_order = _int_param(
            params,
            pipeline_stage_order_field_name(step_number),
            default=step_number,
            min_value=1,
            max_value=MAX_PIPELINE_STEPS,
        )
        grouped[execution_order].append(step_number)

    duplicates = tuple(
        {
            "execution_order": execution_order,
            "stage_numbers": tuple(stage_numbers),
        }
        for execution_order, stage_numbers in sorted(grouped.items())
        if len(stage_numbers) > 1
    )
    if not duplicates:
        return ()

    return (
        AugmentValidationIssue(
            code=DUPLICATE_STAGE_ORDER_CODE,
            message="Each enabled pipeline stage must have a unique execution order.",
            context={
                "reason": "duplicate_execution_order",
                "duplicates": duplicates,
                "visible_step_count": visible_step_count,
            },
        ),
    )


def augment_validation_warning(issues: tuple[AugmentValidationIssue, ...]) -> str:
    """Render validation issues as a compact warning for the FiftyOne form."""

    if not issues:
        return ""

    visible_issues = issues[:VALIDATION_WARNING_LIMIT]
    lines = "\n".join(f"- {issue.message}" for issue in visible_issues)
    omitted_count = len(issues) - len(visible_issues)
    omitted = f"\n- {omitted_count} more validation issue(s) hidden." if omitted_count > 0 else ""
    return f"Fix these settings before running augmentation:\n{lines}{omitted}"


def validation_issues_to_errors(issues: tuple[AugmentValidationIssue, ...]) -> list[JSONDict]:
    """Serialize validation issues as operator result errors."""

    return [issue.to_dict() for issue in issues]


def _pipeline_step_count(params: Mapping[str, object]) -> int:
    return _int_param(
        params,
        PIPELINE_STEP_COUNT_FIELD_NAME,
        default=1,
        min_value=1,
        max_value=MAX_PIPELINE_STEPS,
    )


def _bool_param(params: Mapping[str, object], name: str, *, default: bool) -> bool:
    value = params.get(name)
    return value if isinstance(value, bool) else default


def _int_param(
    params: Mapping[str, object],
    name: str,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    value = params.get(name)
    if isinstance(value, int) and not isinstance(value, bool) and min_value <= value <= max_value:
        return value
    return default


def _string_param(params: Mapping[str, object], name: str) -> str:
    value = params.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else ""


__all__ = [
    "DUPLICATE_STAGE_ORDER_CODE",
    "INVALID_EXECUTION_MODE_CODE",
    "PRESET_SOURCE_CONFLICT_CODE",
    "AugmentValidationIssue",
    "augment_validation_warning",
    "validate_augment_template_sources",
    "validate_effective_augment_params",
    "validate_execution_mode_params",
    "validate_pipeline_stage_orders",
    "validation_issues_to_errors",
]
