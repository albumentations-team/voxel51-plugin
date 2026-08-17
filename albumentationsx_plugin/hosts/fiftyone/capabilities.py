"""Capability browser data model for the FiftyOne App operator."""

from __future__ import annotations

import importlib.metadata
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.catalog.classification import is_mvp_supported_status
from albumentationsx_plugin.core import CapabilityStatus, JSONDict, TransformCapability

ALL_FILTER_VALUE = "all"


class CapabilityCatalogProvider(Protocol):
    """Catalog provider surface needed by the browser service."""

    @property
    def version_info(self) -> Mapping[str, object]:
        """Return package versions that define the capability snapshot."""
        ...

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        """Return every capability entry in deterministic order."""
        ...


@dataclass(frozen=True, slots=True)
class CapabilityBrowserFilters:
    """Search and filter values chosen in the FiftyOne operator form."""

    query: str = ""
    status: str = ALL_FILTER_VALUE
    target: str = ALL_FILTER_VALUE

    @classmethod
    def from_params(cls, params: Mapping[str, object]) -> CapabilityBrowserFilters:
        """Create filters from raw FiftyOne operator params."""

        return cls(
            query=_string_param(params.get("query")),
            status=_filter_param(params.get("status_filter")),
            target=_filter_param(params.get("target_filter")),
        )


@dataclass(frozen=True, slots=True)
class CapabilityBrowserRow:
    """Serializable row shown in the capability browser output."""

    name: str
    status: str
    targets: tuple[str, ...]
    reason_code: str
    message: str
    advanced_parameter_status: str
    advanced_parameters: tuple[str, ...]
    parameter_count: int
    transform_type: str
    module: str
    docstring_short: str

    @classmethod
    def from_capability(cls, capability: TransformCapability) -> CapabilityBrowserRow:
        """Build a display row from one catalog capability entry."""

        parameter_names = _metadata_strings(capability.metadata, "parameter_names")
        return cls(
            name=capability.name,
            status=capability.status.value,
            targets=capability.targets,
            reason_code=capability.reason_code or "",
            message=capability.message or "",
            advanced_parameter_status=_advanced_parameter_status(capability),
            advanced_parameters=capability.advanced_parameters,
            parameter_count=len(parameter_names),
            transform_type=_metadata_string(capability.metadata, "transform_type"),
            module=_metadata_string(capability.metadata, "module"),
            docstring_short=_metadata_string(capability.metadata, "docstring_short"),
        )

    def to_dict(self) -> JSONDict:
        """Serialize the row for FiftyOne output fields."""

        return {
            "name": self.name,
            "status": self.status,
            "targets": ", ".join(self.targets),
            "reason_code": self.reason_code,
            "message": self.message,
            "advanced_parameter_status": self.advanced_parameter_status,
            "advanced_parameters": ", ".join(self.advanced_parameters),
            "parameter_count": self.parameter_count,
            "transform_type": self.transform_type,
            "module": self.module,
            "docstring_short": self.docstring_short,
        }


@dataclass(frozen=True, slots=True)
class CapabilityBrowserResult:
    """Complete read-only payload returned by the browser operator."""

    status: str
    message: str
    plugin_version: str
    fiftyone_version: str
    albumentationsx_version: str
    albu_spec_version: str
    capability_version_key: str
    query: str
    status_filter: str
    target_filter: str
    total_count: int
    matching_count: int
    supported_count: int
    excluded_count: int
    status_counts: Mapping[str, int]
    matching_status_counts: Mapping[str, int]
    rows: tuple[CapabilityBrowserRow, ...]

    def to_dict(self) -> JSONDict:
        """Serialize the browser payload for FiftyOne."""

        row_dicts: list[JSONDict] = [row.to_dict() for row in self.rows]
        return cast(
            JSONDict,
            {
                "status": self.status,
                "message": self.message,
                "plugin_version": self.plugin_version,
                "fiftyone_version": self.fiftyone_version,
                "albumentationsx_version": self.albumentationsx_version,
                "albu_spec_version": self.albu_spec_version,
                "capability_version_key": self.capability_version_key,
                "query": self.query,
                "status_filter": self.status_filter,
                "target_filter": self.target_filter,
                "total_count": self.total_count,
                "matching_count": self.matching_count,
                "supported_count": self.supported_count,
                "excluded_count": self.excluded_count,
                "status_counts_json": json.dumps(dict(self.status_counts), sort_keys=True),
                "matching_status_counts_json": json.dumps(dict(self.matching_status_counts), sort_keys=True),
                "transforms": row_dicts,
                "transforms_json": json.dumps(row_dicts, indent=2, sort_keys=True),
            },
        )


def build_capability_browser_result(
    filters: CapabilityBrowserFilters,
    *,
    provider: CapabilityCatalogProvider | None = None,
) -> CapabilityBrowserResult:
    """Return a filtered capability browser payload."""

    catalog = provider or _default_catalog_provider()
    capabilities = catalog.list_transform_capabilities()
    matching_capabilities = tuple(capability for capability in capabilities if _matches_filters(capability, filters))
    rows = tuple(CapabilityBrowserRow.from_capability(capability) for capability in matching_capabilities)
    version_info = catalog.version_info
    supported_count = sum(1 for capability in capabilities if is_mvp_supported_status(capability.status))

    return CapabilityBrowserResult(
        status="ok",
        message=_result_message(len(rows), len(capabilities)),
        plugin_version=albumentationsx_plugin.__version__,
        fiftyone_version=_dependency_version("fiftyone"),
        albumentationsx_version=str(version_info["albumentationsx"]),
        albu_spec_version=str(version_info["albu_spec"]),
        capability_version_key=_version_key(version_info),
        query=filters.query,
        status_filter=filters.status,
        target_filter=filters.target,
        total_count=len(capabilities),
        matching_count=len(rows),
        supported_count=supported_count,
        excluded_count=len(capabilities) - supported_count,
        status_counts=_status_counts(capabilities),
        matching_status_counts=_status_counts(matching_capabilities),
        rows=rows,
    )


def build_capability_filter_choices(
    *,
    provider: CapabilityCatalogProvider | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return status and target choices available in the current catalog."""

    catalog = provider or _default_catalog_provider()
    capabilities = catalog.list_transform_capabilities()
    statuses = tuple(sorted({capability.status.value for capability in capabilities}))
    targets = tuple(sorted({target for capability in capabilities for target in capability.targets}))
    return (ALL_FILTER_VALUE, *statuses), (ALL_FILTER_VALUE, *targets)


def missing_dependency_browser_result(error: ModuleNotFoundError) -> JSONDict:
    """Return an output payload when catalog runtime dependencies are missing."""

    package_name = _dependency_package_name(error)
    return {
        "status": "error",
        "message": (
            f"Install the '{package_name}' package in the active FiftyOne Python environment, "
            "then reload the FiftyOne App."
        ),
        "plugin_version": albumentationsx_plugin.__version__,
        "fiftyone_version": _dependency_version("fiftyone"),
        "albumentationsx_version": "",
        "albu_spec_version": "",
        "capability_version_key": "",
        "query": "",
        "status_filter": "",
        "target_filter": "",
        "total_count": 0,
        "matching_count": 0,
        "supported_count": 0,
        "excluded_count": 0,
        "status_counts_json": "{}",
        "matching_status_counts_json": "{}",
        "transforms": [],
        "transforms_json": "[]",
    }


def _matches_filters(capability: TransformCapability, filters: CapabilityBrowserFilters) -> bool:
    if filters.query and filters.query.casefold() not in capability.name.casefold():
        return False
    if filters.status != ALL_FILTER_VALUE and capability.status.value != filters.status:
        return False
    return filters.target == ALL_FILTER_VALUE or filters.target in capability.targets


def _status_counts(capabilities: Sequence[TransformCapability]) -> dict[str, int]:
    return dict(sorted(Counter(capability.status.value for capability in capabilities).items()))


def _result_message(matching_count: int, total_count: int) -> str:
    if matching_count == total_count:
        return "Showing every transform capability in the current catalog."
    return f"Showing {matching_count} of {total_count} transform capabilities."


def _advanced_parameter_status(capability: TransformCapability) -> str:
    if not capability.advanced_parameters:
        return "none"
    if capability.status is CapabilityStatus.SUPPORTED_WITH_DEFAULTS:
        return "default_only"
    return "advanced_parameters_present"


def _metadata_string(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _metadata_strings(metadata: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = metadata.get(key)
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value)


def _version_key(version_info: Mapping[str, object]) -> str:
    return f"albumentationsx-{version_info['albumentationsx']}__albu-spec-{version_info['albu_spec']}"


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _string_param(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _filter_param(value: object) -> str:
    value = _string_param(value)
    return value or ALL_FILTER_VALUE


def _dependency_package_name(error: ModuleNotFoundError) -> str:
    module_name = error.name or ""
    return cast(str, {"albumentations": "albumentationsx", "albu_spec": "albu-spec"}.get(module_name, module_name))


def _default_catalog_provider() -> CapabilityCatalogProvider:
    from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider

    return AlbuSpecCatalogProvider()
