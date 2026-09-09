"""Compatibility exports for the original fixed-pipeline import path.

New host code should import the compiler from hosts.fiftyone.pipeline_compiler;
runtime code should import albumentations_backend.image_pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping

from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    FixedImagePipeline as FixedImagePipeline,
)
from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    FixedImagePipelineResult as FixedImagePipelineResult,
)
from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    create_fixed_image_pipeline as create_fixed_image_pipeline,
)
from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    validate_fixed_pipeline_config as validate_fixed_pipeline_config,
)
from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    validate_pipeline_image_shape as validate_pipeline_image_shape,
)
from albumentationsx_plugin.core import ParameterSchemaProvider, PipelineConfig, TransformCatalogProvider


def build_fixed_pipeline_config(
    params: Mapping[str, object],
    *,
    catalog_provider: TransformCatalogProvider | None = None,
    parameter_schema_provider: ParameterSchemaProvider | None = None,
) -> PipelineConfig:
    """Decode legacy operator parameters through the host compiler."""
    from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import build_fixed_pipeline_config as compile_pipeline

    return compile_pipeline(
        params,
        catalog_provider=catalog_provider,
        parameter_schema_provider=parameter_schema_provider,
    )
