"""albu-spec catalog provider implementation."""

from __future__ import annotations

import importlib.metadata
from collections import Counter
from functools import cached_property
from typing import Any

from albu_spec import get_all_transforms_metadata

from albumentationsx_plugin.albumentations_backend.catalog.classification import (
    classify_transform_metadata,
    is_mvp_supported_status,
)
from albumentationsx_plugin.core import JSONDict, TransformCapability, TransformCatalogProvider
from albumentationsx_plugin.core.serialization import normalize_json_mapping


class AlbuSpecCatalogProvider:
    """Read transform metadata from albu-spec and expose neutral capabilities."""

    @cached_property
    def version_info(self) -> JSONDict:
        """Return versions that define the generated catalog snapshot."""

        return {
            "albumentationsx": _dependency_version("albumentationsx"),
            "albu_spec": _dependency_version("albu-spec"),
        }

    @cached_property
    def _capabilities(self) -> tuple[TransformCapability, ...]:
        collection = get_all_transforms_metadata()
        capabilities = tuple(classify_transform_metadata(metadata) for metadata in collection.get_all())
        return tuple(sorted(capabilities, key=lambda capability: capability.name))

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        """Return every albu-spec transform with its plugin support status."""

        return self._capabilities

    def get_transform_capability(self, name: str) -> TransformCapability | None:
        """Return one transform capability entry by public transform name."""

        for capability in self._capabilities:
            if capability.name == name:
                return capability
        return None

    def list_supported_transform_names(self) -> tuple[str, ...]:
        """Return transform names exposed as normal MVP choices."""

        return tuple(capability.name for capability in self._capabilities if is_mvp_supported_status(capability.status))

    def build_snapshot(self, *, include_capabilities: bool = False) -> JSONDict:
        """Build a deterministic snapshot summary used by tests and reports."""

        capabilities = self._capabilities
        status_counts = Counter(capability.status.value for capability in capabilities)
        snapshot: dict[str, Any] = {
            "version_key": _version_key(self.version_info),
            "versions": dict(self.version_info),
            "total_count": len(capabilities),
            "supported_count": len(self.list_supported_transform_names()),
            "status_counts": dict(sorted(status_counts.items())),
            "supported_transform_names": list(self.list_supported_transform_names()),
        }
        if include_capabilities:
            snapshot["capabilities"] = [capability.to_dict() for capability in capabilities]
        return normalize_json_mapping(snapshot)


def build_default_catalog_provider() -> TransformCatalogProvider:
    """Create the default albu-spec-backed transform catalog provider."""

    return AlbuSpecCatalogProvider()


def build_albu_spec_catalog_snapshot(*, include_capabilities: bool = False) -> JSONDict:
    """Build a deterministic snapshot of the current albu-spec catalog."""

    return AlbuSpecCatalogProvider().build_snapshot(include_capabilities=include_capabilities)


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _version_key(version_info: JSONDict) -> str:
    return f"albumentationsx-{version_info['albumentationsx']}__albu-spec-{version_info['albu_spec']}"
