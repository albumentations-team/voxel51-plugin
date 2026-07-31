"""Grouped host-neutral DTO contracts."""

from albumentationsx_plugin.core.contracts.augmentation import AugmentationInput, AugmentationResult
from albumentationsx_plugin.core.contracts.catalog import CapabilityStatus, TransformCapability
from albumentationsx_plugin.core.contracts.forms import FieldKind, FormFieldSchema
from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig, TransformConfig
from albumentationsx_plugin.core.contracts.runs import RunManifest

__all__ = [
    "AugmentationInput",
    "AugmentationResult",
    "CapabilityStatus",
    "FieldKind",
    "FormFieldSchema",
    "PipelineConfig",
    "RunManifest",
    "TransformCapability",
    "TransformConfig",
]
