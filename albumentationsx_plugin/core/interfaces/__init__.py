"""Protocol interfaces shared across plugin layers."""

from albumentationsx_plugin.core.interfaces.catalog import ParameterSchemaProvider, TransformCatalogProvider
from albumentationsx_plugin.core.interfaces.host import HostSampleAdapter
from albumentationsx_plugin.core.interfaces.pipeline import PipelineFactory, PipelineRunner
from albumentationsx_plugin.core.interfaces.storage import OutputStorageBackend, RunStore

__all__ = [
    "HostSampleAdapter",
    "OutputStorageBackend",
    "ParameterSchemaProvider",
    "PipelineFactory",
    "PipelineRunner",
    "RunStore",
    "TransformCatalogProvider",
]
