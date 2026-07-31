"""Transform catalog contracts shared by backend and host adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from albumentationsx_plugin.core.serialization import (
    JSONDict,
    normalize_json_mapping,
    optional_str,
    require_mapping,
    require_str,
    string_tuple,
)


class CapabilityStatus(StrEnum):
    """Support status for an Albumentations transform in the plugin catalog."""

    SUPPORTED = "supported"
    SUPPORTED_WITH_DEFAULTS = "supported_with_defaults"
    REQUIRES_EXTERNAL_DATA = "requires_external_data"
    UNSUPPORTED_OUTPUT = "unsupported_output"
    UNSUPPORTED_TARGET = "unsupported_target"
    UNSUPPORTED_SCHEMA = "unsupported_schema"


@dataclass(frozen=True, slots=True)
class TransformCapability:
    """Catalog entry describing whether and how a transform can be used.

    The backend owns capability decisions. Host adapters should treat this as
    display and filtering data, not as permission to instantiate transforms.
    """

    name: str
    status: CapabilityStatus
    targets: tuple[str, ...] = ("image",)
    reason_code: str | None = None
    message: str | None = None
    advanced_parameters: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_str(self.name, "name"))
        object.__setattr__(self, "status", CapabilityStatus(self.status))
        object.__setattr__(self, "targets", string_tuple(self.targets, "targets"))
        object.__setattr__(self, "reason_code", optional_str(self.reason_code, "reason_code"))
        object.__setattr__(self, "message", optional_str(self.message, "message"))
        object.__setattr__(
            self,
            "advanced_parameters",
            string_tuple(self.advanced_parameters, "advanced_parameters"),
        )
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the capability entry for reports and snapshots."""

        return cast(
            JSONDict,
            {
                "name": self.name,
                "status": self.status.value,
                "targets": list(self.targets),
                "reason_code": self.reason_code,
                "message": self.message,
                "advanced_parameters": list(self.advanced_parameters),
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TransformCapability:
        """Create a capability entry from a decoded JSON object."""

        return cls(
            name=require_str(value.get("name"), "name"),
            status=CapabilityStatus(require_str(value.get("status"), "status")),
            targets=string_tuple(value.get("targets"), "targets"),
            reason_code=optional_str(value.get("reason_code"), "reason_code"),
            message=optional_str(value.get("message"), "message"),
            advanced_parameters=string_tuple(value.get("advanced_parameters"), "advanced_parameters"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )
