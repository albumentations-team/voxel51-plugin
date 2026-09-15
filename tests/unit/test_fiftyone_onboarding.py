from __future__ import annotations

import importlib
import sys

import pytest

from albumentationsx_plugin.core import DEFAULT_TRANSFORM_PROBABILITY, RUN_LABEL_FIELD_NAME
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.onboarding import (
    FIRST_RUN_OUTPUTS_PER_SAMPLE,
    FIRST_RUN_RUN_LABEL,
    FIRST_RUN_STEP_COUNT,
    FIRST_RUN_TRANSFORM_NAME,
    OUTPUTS_PER_SAMPLE_FIELD_NAME,
    PROBABILITY_FIELD_NAME,
    TRANSFORM_FIELD_NAME,
    first_run_augment_params,
    first_run_pipeline_config,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import PREVIEW_ONLY_FIELD_NAME


@pytest.mark.unit
def test_fiftyone_onboarding_import_does_not_import_runtime_integrations() -> None:
    for module_name in (
        "albumentationsx_plugin.hosts.fiftyone.onboarding",
        "fiftyone",
        "albumentations",
        "albu_spec",
    ):
        sys.modules.pop(module_name, None)

    importlib.import_module("albumentationsx_plugin.hosts.fiftyone.onboarding")

    assert "fiftyone" not in sys.modules
    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_first_run_pipeline_config_uses_safe_demo_transform() -> None:
    config = first_run_pipeline_config()

    assert config.outputs_per_sample == FIRST_RUN_OUTPUTS_PER_SAMPLE
    assert config.options == {"source": "first_run_onboarding"}
    assert len(config.transforms) == FIRST_RUN_STEP_COUNT
    assert config.transforms[0].name == FIRST_RUN_TRANSFORM_NAME
    assert config.transforms[0].params == {PROBABILITY_FIELD_NAME: DEFAULT_TRANSFORM_PROBABILITY}


@pytest.mark.unit
def test_first_run_augment_params_match_guided_selected_sample_workflow() -> None:
    params = first_run_augment_params()

    assert params[EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_SELECTED_SAMPLES
    assert params[RUN_LABEL_FIELD_NAME] == FIRST_RUN_RUN_LABEL
    assert params[TRANSFORM_FIELD_NAME] == FIRST_RUN_TRANSFORM_NAME
    assert params[PROBABILITY_FIELD_NAME] == DEFAULT_TRANSFORM_PROBABILITY
    assert params[OUTPUTS_PER_SAMPLE_FIELD_NAME] == FIRST_RUN_OUTPUTS_PER_SAMPLE
    assert params[PREVIEW_ONLY_FIELD_NAME] is False
    assert params["dry_run"] is False


@pytest.mark.unit
def test_first_run_augment_params_support_preview_and_dry_run_modes() -> None:
    preview_params = first_run_augment_params(preview_only=True)
    dry_run_params = first_run_augment_params(dry_run=True)

    assert preview_params[PREVIEW_ONLY_FIELD_NAME] is True
    assert preview_params["dry_run"] is False
    assert dry_run_params[PREVIEW_ONLY_FIELD_NAME] is False
    assert dry_run_params["dry_run"] is True
