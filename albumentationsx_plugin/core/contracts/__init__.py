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
)
from albumentationsx_plugin.core.contracts.forms import FieldKind, FormFieldSchema
from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig, TransformConfig
from albumentationsx_plugin.core.contracts.runs import RunManifest

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
    "MAX_OUTPUTS_PER_SAMPLE",
    "PipelineConfig",
    "RunManifest",
    "TransformCapability",
    "TransformConfig",
]
