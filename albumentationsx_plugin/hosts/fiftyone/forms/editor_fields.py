"""Shared augmentation editor field names."""

from __future__ import annotations

from typing import Final

TRANSFORM_FIELD_NAME: Final[str] = "transform"
PROBABILITY_FIELD_NAME: Final[str] = "p"
OUTPUTS_PER_SAMPLE_FIELD_NAME: Final[str] = "outputs_per_sample"
DEFAULT_DYNAMIC_TRANSFORM_NAME: Final[str] = "HorizontalFlip"
PIPELINE_STEP_COUNT_LABEL: Final[str] = "Pipeline stages"
PIPELINE_STAGE_ENABLED_LABEL: Final[str] = "Enabled"
PIPELINE_STAGE_ORDER_LABEL: Final[str] = "Execution order"
RANDOM_CROP_TRANSFORM_NAME: Final[str] = "RandomCrop"
GENERAL_SECTION_FIELD_NAME: Final[str] = "_general_settings"
ANNOTATION_SECTION_FIELD_NAME: Final[str] = "_annotation_settings"
ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME: Final[str] = "_annotation_compatibility_warning"
STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage"
ADVANCED_STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage_advanced"
AUGMENT_VALIDATION_WARNING_FIELD_NAME: Final[str] = "_augment_validation_warning"
EXECUTION_MODE_GUIDANCE_FIELD_NAME: Final[str] = "_execution_mode_guidance"
