"""First-run onboarding defaults for the FiftyOne augmentation workflow."""

from __future__ import annotations

from typing import Final

from albumentationsx_plugin.core import (
    DEFAULT_TRANSFORM_PROBABILITY,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    RUN_LABEL_FIELD_NAME,
    PipelineConfig,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import PREVIEW_ONLY_FIELD_NAME

FIRST_RUN_RUN_LABEL: Final[str] = "First run demo"
FIRST_RUN_TRANSFORM_NAME: Final[str] = "HorizontalFlip"
FIRST_RUN_OUTPUTS_PER_SAMPLE: Final[int] = 1
FIRST_RUN_STEP_COUNT: Final[int] = 1
OUTPUTS_PER_SAMPLE_FIELD_NAME: Final[str] = "outputs_per_sample"
PROBABILITY_FIELD_NAME: Final[str] = "p"
TRANSFORM_FIELD_NAME: Final[str] = "transform"


def first_run_pipeline_config() -> PipelineConfig:
    """Return the safest starter pipeline for the generated demo dataset."""

    return PipelineConfig(
        transforms=(
            TransformConfig(
                name=FIRST_RUN_TRANSFORM_NAME,
                params={PROBABILITY_FIELD_NAME: DEFAULT_TRANSFORM_PROBABILITY},
            ),
        ),
        outputs_per_sample=FIRST_RUN_OUTPUTS_PER_SAMPLE,
        options={"source": "first_run_onboarding"},
    )


def first_run_augment_params(*, preview_only: bool = False, dry_run: bool = False) -> dict[str, object]:
    """Return operator params for the guided first-run augmentation."""

    return {
        EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
        RUN_LABEL_FIELD_NAME: FIRST_RUN_RUN_LABEL,
        PIPELINE_STEP_COUNT_FIELD_NAME: FIRST_RUN_STEP_COUNT,
        TRANSFORM_FIELD_NAME: FIRST_RUN_TRANSFORM_NAME,
        PROBABILITY_FIELD_NAME: DEFAULT_TRANSFORM_PROBABILITY,
        OUTPUTS_PER_SAMPLE_FIELD_NAME: FIRST_RUN_OUTPUTS_PER_SAMPLE,
        PREVIEW_ONLY_FIELD_NAME: preview_only,
        "dry_run": dry_run,
    }


__all__ = [
    "FIRST_RUN_OUTPUTS_PER_SAMPLE",
    "FIRST_RUN_RUN_LABEL",
    "FIRST_RUN_STEP_COUNT",
    "FIRST_RUN_TRANSFORM_NAME",
    "OUTPUTS_PER_SAMPLE_FIELD_NAME",
    "PROBABILITY_FIELD_NAME",
    "TRANSFORM_FIELD_NAME",
    "first_run_augment_params",
    "first_run_pipeline_config",
]
