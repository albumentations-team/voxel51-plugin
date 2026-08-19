"""Grouped host-neutral DTO contracts."""

from albumentationsx_plugin.core.contracts.augmentation import AugmentationInput, AugmentationResult
from albumentationsx_plugin.core.contracts.catalog import CapabilityStatus, TransformCapability
from albumentationsx_plugin.core.contracts.fixed_slice import (
    DEFAULT_BRIGHTNESS_RANGE,
    DEFAULT_CONTRAST_RANGE,
    DEFAULT_CROP_SIZE,
    DEFAULT_TRANSFORM_PROBABILITY,
    FIXED_TRANSFORM_NAMES,
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
    PIPELINE_STAGE_ENABLED_FIELD_NAME,
    PIPELINE_STAGE_ORDER_FIELD_NAME,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.core.contracts.forms import FieldKind, FormFieldSchema
from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig, TransformConfig
from albumentationsx_plugin.core.contracts.runs import (
    RUN_CLEANED_AT_METADATA_KEY,
    RUN_CLEANUP_STATUS_CLEANED,
    RUN_CLEANUP_STATUS_METADATA_KEY,
    RUN_LABEL_FIELD_NAME,
    RUN_LABEL_SLUG_METADATA_KEY,
    RunManifest,
)

__all__ = [
    "AugmentationInput",
    "AugmentationResult",
    "CapabilityStatus",
    "DEFAULT_BRIGHTNESS_RANGE",
    "DEFAULT_CONTRAST_RANGE",
    "DEFAULT_CROP_SIZE",
    "DEFAULT_TRANSFORM_PROBABILITY",
    "FieldKind",
    "FIXED_TRANSFORM_NAMES",
    "FormFieldSchema",
    "MAX_PIPELINE_STEPS",
    "MAX_OUTPUTS_PER_SAMPLE",
    "PIPELINE_STEP_COUNT_FIELD_NAME",
    "PIPELINE_STAGE_ENABLED_FIELD_NAME",
    "PIPELINE_STAGE_ORDER_FIELD_NAME",
    "PipelineConfig",
    "RUN_CLEANED_AT_METADATA_KEY",
    "RUN_CLEANUP_STATUS_CLEANED",
    "RUN_CLEANUP_STATUS_METADATA_KEY",
    "RUN_LABEL_FIELD_NAME",
    "RUN_LABEL_SLUG_METADATA_KEY",
    "RunManifest",
    "TransformCapability",
    "TransformConfig",
    "pipeline_stage_enabled_field_name",
    "pipeline_stage_order_field_name",
    "pipeline_step_field_name",
]
