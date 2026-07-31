"""Catalog-driven AlbumentationsX pipeline construction and replay."""

from albumentationsx_plugin.albumentations_backend.pipeline.factory import (
    AlbumentationsPipelineFactory,
    build_default_pipeline_factory,
)
from albumentationsx_plugin.albumentations_backend.pipeline.registry import (
    AlbumentationsTransformRegistry,
    build_default_transform_registry,
)
from albumentationsx_plugin.albumentations_backend.pipeline.replay import extract_replay
from albumentationsx_plugin.albumentations_backend.pipeline.runner import (
    AlbumentationsImagePipelineResult,
    AlbumentationsImagePipelineRunner,
    validate_rgb_array,
)

__all__ = [
    "AlbumentationsImagePipelineResult",
    "AlbumentationsImagePipelineRunner",
    "AlbumentationsPipelineFactory",
    "AlbumentationsTransformRegistry",
    "build_default_pipeline_factory",
    "build_default_transform_registry",
    "extract_replay",
    "validate_rgb_array",
]
