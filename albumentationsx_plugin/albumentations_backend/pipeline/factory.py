"""Catalog-driven AlbumentationsX pipeline factory."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import albumentations as A

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.parameters import (
    AlbuSpecParameterSchemaProvider,
)
from albumentationsx_plugin.albumentations_backend.pipeline.coercion import coerce_transform_params
from albumentationsx_plugin.albumentations_backend.pipeline.registry import (
    AlbumentationsTransformRegistry,
    build_default_transform_registry,
)
from albumentationsx_plugin.albumentations_backend.pipeline.runner import AlbumentationsImagePipelineRunner
from albumentationsx_plugin.core import (
    InvalidParameterError,
    ParameterSchemaProvider,
    PipelineConfig,
    TransformConfig,
)


@dataclass(frozen=True, slots=True)
class AlbumentationsPipelineFactory:
    """Validate configs and create AlbumentationsX replay runners."""

    registry: AlbumentationsTransformRegistry = field(default_factory=build_default_transform_registry)
    parameter_schema_provider: ParameterSchemaProvider = field(
        default_factory=lambda: AlbuSpecParameterSchemaProvider(catalog_provider=AlbuSpecCatalogProvider()),
    )

    def validate(self, config: PipelineConfig) -> None:
        """Raise a structured error when a pipeline config cannot be executed."""

        if not config.transforms:
            raise InvalidParameterError(
                transform_name="<pipeline>",
                parameter_name="transforms",
                message="Pipeline must contain at least one transform.",
                context={"reason_code": "empty_pipeline"},
            )
        self._build_transforms(config.transforms)

    def create_runner(self, config: PipelineConfig) -> AlbumentationsImagePipelineRunner:
        """Create a replay runner for a validated pipeline config."""

        transforms = self._build_transforms(config.transforms)
        return AlbumentationsImagePipelineRunner(config=config, transforms=transforms)

    def _build_transforms(self, transforms: Sequence[TransformConfig]) -> tuple[A.BasicTransform, ...]:
        return tuple(self._build_transform(transform) for transform in transforms)

    def _build_transform(self, transform: TransformConfig) -> A.BasicTransform:
        transform_class = self.registry.get_transform_class(transform.name)
        schema = self.parameter_schema_provider.get_parameter_schema(transform.name)
        params = coerce_transform_params(transform, schema)
        try:
            return transform_class(**cast(dict[str, Any], params))
        except (TypeError, ValueError) as error:
            raise InvalidParameterError(
                transform_name=transform.name,
                parameter_name="<constructor>",
                message=f"{transform.name} rejected the supplied parameters.",
                context={
                    "reason_code": "albumentations_constructor_error",
                    "error": str(error),
                },
            ) from error


def build_default_pipeline_factory() -> AlbumentationsPipelineFactory:
    """Create the default catalog-driven AlbumentationsX pipeline factory."""

    return AlbumentationsPipelineFactory()
