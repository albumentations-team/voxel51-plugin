"""Host-neutral contracts for the AlbumentationsX plugin."""

from albumentationsx_plugin.core.errors import (
    ErrorCode,
    HostAdapterError,
    InvalidParameterError,
    MediaIOError,
    PluginError,
    UnsupportedTransformError,
)
from albumentationsx_plugin.core.interfaces import (
    HostSampleAdapter,
    OutputStorageBackend,
    ParameterSchemaProvider,
    PipelineFactory,
    PipelineRunner,
    RunStore,
    TransformCatalogProvider,
)
from albumentationsx_plugin.core.models import (
    AugmentationInput,
    AugmentationResult,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    JSONDict,
    JSONValue,
    PipelineConfig,
    RunManifest,
    TransformCapability,
    TransformConfig,
)

__all__ = [
    "AugmentationInput",
    "AugmentationResult",
    "CapabilityStatus",
    "ErrorCode",
    "FieldKind",
    "FormFieldSchema",
    "HostSampleAdapter",
    "HostAdapterError",
    "InvalidParameterError",
    "JSONDict",
    "JSONValue",
    "MediaIOError",
    "OutputStorageBackend",
    "ParameterSchemaProvider",
    "PipelineConfig",
    "PipelineFactory",
    "PipelineRunner",
    "PluginError",
    "RunManifest",
    "RunStore",
    "TransformCapability",
    "TransformCatalogProvider",
    "TransformConfig",
    "UnsupportedTransformError",
]
