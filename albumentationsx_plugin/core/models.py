"""Compatibility exports for host-neutral core models.

The concrete DTOs live in smaller modules grouped by responsibility. This
module keeps `albumentationsx_plugin.core.models` as a stable import path for
callers that want all model contracts from one place.
"""

from albumentationsx_plugin.core.contracts.augmentation import AugmentationInput, AugmentationResult
from albumentationsx_plugin.core.contracts.catalog import CapabilityStatus, TransformCapability
from albumentationsx_plugin.core.contracts.forms import FieldKind, FormFieldSchema
from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig, TransformConfig
from albumentationsx_plugin.core.contracts.runs import RunManifest
from albumentationsx_plugin.core.serialization import JSONDict, JSONValue, normalize_json_mapping, normalize_json_value

__all__ = [
    "AugmentationInput",
    "AugmentationResult",
    "CapabilityStatus",
    "FieldKind",
    "FormFieldSchema",
    "JSONDict",
    "JSONValue",
    "PipelineConfig",
    "RunManifest",
    "TransformCapability",
    "TransformConfig",
    "normalize_json_mapping",
    "normalize_json_value",
]
