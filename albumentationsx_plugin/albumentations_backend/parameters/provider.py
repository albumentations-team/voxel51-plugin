"""albu-spec parameter schema provider implementation."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from albu_spec import get_all_transforms_metadata

from albumentationsx_plugin.albumentations_backend.catalog import (
    AlbuSpecCatalogProvider,
    build_albu_spec_catalog_snapshot,
)
from albumentationsx_plugin.albumentations_backend.catalog.classification import is_mvp_supported_status
from albumentationsx_plugin.albumentations_backend.parameters.conversion import build_transform_parameter_schema
from albumentationsx_plugin.core import (
    FormFieldSchema,
    JSONDict,
    ParameterSchemaProvider,
    TransformCatalogProvider,
    UnsupportedTransformError,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping


class AlbuSpecParameterSchemaProvider:
    """Generate neutral parameter schemas from albu-spec transform metadata."""

    def __init__(self, catalog_provider: TransformCatalogProvider | None = None) -> None:
        self._catalog_provider = catalog_provider or AlbuSpecCatalogProvider()

    @cached_property
    def _metadata_by_name(self) -> dict[str, Any]:
        collection = get_all_transforms_metadata()
        return {metadata.name: metadata for metadata in collection.get_all()}

    @cached_property
    def _schemas_by_name(self) -> dict[str, tuple[FormFieldSchema, ...]]:
        return {
            transform_name: build_transform_parameter_schema(metadata)
            for transform_name, metadata in sorted(self._metadata_by_name.items())
        }

    def get_parameter_schema(self, transform_name: str) -> tuple[FormFieldSchema, ...]:
        """Return neutral fields for a transform that is exposed by the MVP catalog."""

        capability = self._catalog_provider.get_transform_capability(transform_name)
        if capability is None:
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} is not known to the albu-spec catalog.",
                context={"reason_code": "unknown_transform"},
            )
        if not is_mvp_supported_status(capability.status):
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} is not available for MVP parameter schema generation.",
                context={
                    "reason_code": capability.reason_code or capability.status.value,
                    "status": capability.status.value,
                },
            )
        return self._schemas_by_name[transform_name]

    def build_snapshot(self, transform_names: tuple[str, ...]) -> JSONDict:
        """Build a deterministic JSON snapshot for selected transform schemas."""

        snapshot = {
            "version_key": build_albu_spec_catalog_snapshot(include_capabilities=False)["version_key"],
            "transform_names": list(transform_names),
            "schemas": {
                transform_name: [field.to_dict() for field in self.get_parameter_schema(transform_name)]
                for transform_name in transform_names
            },
        }
        return normalize_json_mapping(snapshot)


def build_default_parameter_schema_provider() -> ParameterSchemaProvider:
    """Create the default albu-spec-backed parameter schema provider."""

    return AlbuSpecParameterSchemaProvider()


def build_albu_spec_parameter_schema_snapshot(transform_names: tuple[str, ...]) -> JSONDict:
    """Build a deterministic snapshot of selected albu-spec parameter schemas."""

    return AlbuSpecParameterSchemaProvider().build_snapshot(transform_names)
