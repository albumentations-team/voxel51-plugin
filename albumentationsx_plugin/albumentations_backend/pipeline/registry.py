"""Safe transform class lookup backed by albu-spec metadata."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import Any, cast

import albumentations as A
from albu_spec import get_all_transforms_metadata

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.catalog.classification import is_mvp_supported_status
from albumentationsx_plugin.core import TransformCatalogProvider, UnsupportedTransformError


@dataclass(frozen=True)
class AlbumentationsTransformRegistry:
    """Resolve only catalog-verified AlbumentationsX transform names."""

    catalog_provider: TransformCatalogProvider

    @cached_property
    def _metadata_by_name(self) -> Mapping[str, Any]:
        collection = get_all_transforms_metadata()
        return {metadata.name: metadata for metadata in collection.get_all()}

    def get_transform_class(self, transform_name: str) -> type[A.BasicTransform]:
        """Return the AlbumentationsX class for a supported catalog transform."""

        capability = self.catalog_provider.get_transform_capability(transform_name)
        if capability is None:
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} is not known to the albu-spec catalog.",
                context={"reason_code": "unknown_transform"},
            )
        if not is_mvp_supported_status(capability.status):
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} is not available for image-only MVP execution.",
                context={
                    "reason_code": capability.reason_code or capability.status.value,
                    "status": capability.status.value,
                },
            )

        metadata = self._metadata_by_name.get(transform_name)
        if metadata is None:
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} has no albu-spec runtime metadata.",
                context={"reason_code": "missing_runtime_metadata"},
            )

        module_name = getattr(metadata, "module", None)
        if not isinstance(module_name, str) or not module_name.startswith("albumentations."):
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} cannot be resolved from a trusted Albumentations module.",
                context={"reason_code": "untrusted_transform_module", "module": module_name},
            )

        module = importlib.import_module(module_name)
        transform_class = getattr(module, transform_name, None)
        if not isinstance(transform_class, type) or not issubclass(transform_class, A.BasicTransform):
            raise UnsupportedTransformError(
                transform_name,
                message=f"Transform {transform_name} did not resolve to an Albumentations transform class.",
                context={"reason_code": "invalid_transform_class", "module": module_name},
            )
        return cast(type[A.BasicTransform], transform_class)


def build_default_transform_registry() -> AlbumentationsTransformRegistry:
    """Create the default transform registry."""

    return AlbumentationsTransformRegistry(catalog_provider=AlbuSpecCatalogProvider())
