from __future__ import annotations

from typing import Any, cast

import pytest

from albumentationsx_plugin.core import (
    PIPELINE_STEP_COUNT_FIELD_NAME,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    DUPLICATE_STAGE_ORDER_CODE,
    INVALID_EXECUTION_MODE_CODE,
    PRESET_SOURCE_CONFLICT_CODE,
    augment_validation_warning,
    validate_augment_template_sources,
    validate_effective_augment_params,
    validate_execution_mode_params,
    validate_pipeline_stage_orders,
    validation_issues_to_errors,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    PIPELINE_PRESET_KEY_FIELD_NAME,
    SAVE_PRESET_NAME_FIELD_NAME,
    SAVE_PRESET_ONLY_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.presets import PREVIOUS_RUN_KEY_FIELD_NAME
from albumentationsx_plugin.hosts.fiftyone.preview_contract import PREVIEW_ONLY_FIELD_NAME


@pytest.mark.unit
def test_validate_augment_template_sources_rejects_named_preset_and_previous_run() -> None:
    issues = validate_augment_template_sources(
        {
            PIPELINE_PRESET_KEY_FIELD_NAME: "training-defaults",
            PREVIOUS_RUN_KEY_FIELD_NAME: "albumentationsx-20260731T120000Z-run",
        }
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == PRESET_SOURCE_CONFLICT_CODE
    assert issue.context["pipeline_preset_key"] == "training-defaults"
    assert issue.context["previous_run_key"] == "albumentationsx-20260731T120000Z-run"


@pytest.mark.unit
def test_validate_pipeline_stage_orders_rejects_duplicate_enabled_orders() -> None:
    issues = validate_pipeline_stage_orders(
        {
            PIPELINE_STEP_COUNT_FIELD_NAME: 3,
            pipeline_stage_order_field_name(1): 1,
            pipeline_stage_order_field_name(2): 1,
            pipeline_stage_order_field_name(3): 3,
        }
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == DUPLICATE_STAGE_ORDER_CODE
    context = cast(dict[str, Any], issue.to_dict()["context"])
    assert context["duplicates"] == [{"execution_order": 1, "stage_numbers": [1, 2]}]


@pytest.mark.unit
def test_validate_pipeline_stage_orders_ignores_disabled_duplicate_orders() -> None:
    assert (
        validate_pipeline_stage_orders(
            {
                PIPELINE_STEP_COUNT_FIELD_NAME: 3,
                pipeline_stage_order_field_name(1): 1,
                pipeline_stage_order_field_name(2): 1,
                pipeline_stage_enabled_field_name(2): False,
                pipeline_stage_order_field_name(3): 3,
            }
        )
        == ()
    )


@pytest.mark.unit
def test_validate_execution_mode_params_rejects_ambiguous_preview_dry_run_and_preset_save() -> None:
    issues = validate_execution_mode_params(
        {
            PREVIEW_ONLY_FIELD_NAME: True,
            "dry_run": True,
            SAVE_PRESET_NAME_FIELD_NAME: "Debug preset",
        }
    )

    assert [issue.code for issue in issues] == [
        INVALID_EXECUTION_MODE_CODE,
        INVALID_EXECUTION_MODE_CODE,
        INVALID_EXECUTION_MODE_CODE,
    ]
    assert {issue.context["reason"] for issue in issues} == {
        "preview_only_conflicts_with_dry_run",
        "preview_only_would_skip_preset_save",
        "dry_run_would_skip_preset_save",
    }


@pytest.mark.unit
def test_validate_execution_mode_params_requires_name_for_save_preset_only() -> None:
    issues = validate_execution_mode_params({SAVE_PRESET_ONLY_FIELD_NAME: True})

    assert len(issues) == 1
    assert issues[0].code == INVALID_EXECUTION_MODE_CODE
    assert issues[0].context["reason"] == "save_preset_only_requires_preset_name"


@pytest.mark.unit
def test_validate_effective_augment_params_allows_supported_mode_combinations() -> None:
    assert validate_effective_augment_params({PREVIEW_ONLY_FIELD_NAME: True}) == ()
    assert validate_effective_augment_params({"dry_run": True}) == ()
    assert (
        validate_effective_augment_params(
            {
                SAVE_PRESET_ONLY_FIELD_NAME: True,
                SAVE_PRESET_NAME_FIELD_NAME: "Training defaults",
            }
        )
        == ()
    )
    assert (
        validate_effective_augment_params(
            {
                SAVE_PRESET_NAME_FIELD_NAME: "Training defaults",
            }
        )
        == ()
    )


@pytest.mark.unit
def test_validation_issues_render_as_form_warning_and_operator_errors() -> None:
    issues = validate_augment_template_sources(
        {
            PIPELINE_PRESET_KEY_FIELD_NAME: "training-defaults",
            PREVIOUS_RUN_KEY_FIELD_NAME: "albumentationsx-20260731T120000Z-run",
        }
    )

    warning = augment_validation_warning(issues)
    errors = validation_issues_to_errors(issues)

    assert "Fix these settings before running augmentation" in warning
    assert "Choose either a named preset or a previous run" in warning
    first_error = cast(dict[str, Any], errors[0])
    assert first_error["code"] == PRESET_SOURCE_CONFLICT_CODE
