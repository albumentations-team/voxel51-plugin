"""Backend-facing interfaces for AlbumentationsX integration.

Concrete backend modules should implement these protocols while keeping
AlbumentationsX and albu-spec version-specific details out of host adapters.
"""

from albumentationsx_plugin.core.interfaces import (
    ParameterSchemaProvider,
    PipelineFactory,
    PipelineRunner,
    TransformCatalogProvider,
)

__all__ = [
    "ParameterSchemaProvider",
    "PipelineFactory",
    "PipelineRunner",
    "TransformCatalogProvider",
]
