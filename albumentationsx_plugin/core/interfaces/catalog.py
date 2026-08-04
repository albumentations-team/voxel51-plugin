"""Catalog and schema provider interfaces.

Backends implement these protocols to expose transform metadata without leaking
source-specific data structures into host adapters.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from albumentationsx_plugin.core.contracts import FormFieldSchema, TransformCapability


@runtime_checkable
class TransformCatalogProvider(Protocol):
    """Read-only transform capability catalog."""

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        """Return every known transform with its support status."""
        ...

    def get_transform_capability(self, name: str) -> TransformCapability | None:
        """Return one transform capability entry by public transform name."""
        ...


@runtime_checkable
class ParameterSchemaProvider(Protocol):
    """Provider for host-neutral transform parameter schemas."""

    def get_parameter_schema(self, transform_name: str) -> tuple[FormFieldSchema, ...]:
        """Return neutral form fields for a supported transform."""
        ...
