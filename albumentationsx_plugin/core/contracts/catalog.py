"""Transform catalog contracts shared by backend and host adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from albumentationsx_plugin._compat import StrEnum
from albumentationsx_plugin.core.serialization import (
    JSONDict,
    mapping_tuple,
    normalize_json_mapping,
    optional_str,
    require_bool,
    require_mapping,
    require_str,
    string_tuple,
)


class CapabilityStatus(StrEnum):
    """Support status for an Albumentations transform in the plugin catalog."""

    SUPPORTED = "supported"
    SUPPORTED_WITH_DEFAULTS = "supported_with_defaults"
    HIDDEN = "hidden"
    REQUIRES_MANUAL_SCHEMA = "requires_manual_schema"
    REQUIRES_EXTERNAL_DATA = "requires_external_data"
    BLOCKED_MEDIA_TARGET = "blocked_media_target"
    UNSUPPORTED = "unsupported"
    UNSUPPORTED_OUTPUT = "unsupported_output"
    UNSUPPORTED_TARGET = "unsupported_target"
    UNSUPPORTED_SCHEMA = "unsupported_schema"


class ExternalInputKind(StrEnum):
    """Shape of non-sample input data required by an Albumentations transform."""

    METADATA_SEQUENCE = "metadata_sequence"
    FILE_PATH = "file_path"


@dataclass(frozen=True, slots=True)
class ExternalInputRequirement:
    """External input contract for transforms that cannot run from one image alone."""

    name: str
    kind: ExternalInputKind
    parameter_name: str | None = None
    metadata_key: str | None = None
    required: bool = True
    resolver: str | None = None
    description: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_str(self.name, "name"))
        object.__setattr__(self, "kind", ExternalInputKind(self.kind))
        object.__setattr__(self, "parameter_name", optional_str(self.parameter_name, "parameter_name"))
        object.__setattr__(self, "metadata_key", optional_str(self.metadata_key, "metadata_key"))
        object.__setattr__(self, "required", require_bool(self.required, "required"))
        object.__setattr__(self, "resolver", optional_str(self.resolver, "resolver"))
        object.__setattr__(self, "description", optional_str(self.description, "description"))
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the external input requirement for reports and snapshots."""

        return cast(
            JSONDict,
            {
                "name": self.name,
                "kind": self.kind.value,
                "parameter_name": self.parameter_name,
                "metadata_key": self.metadata_key,
                "required": self.required,
                "resolver": self.resolver,
                "description": self.description,
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ExternalInputRequirement:
        """Create an external input requirement from a decoded JSON object."""

        return cls(
            name=require_str(value.get("name"), "name"),
            kind=ExternalInputKind(require_str(value.get("kind"), "kind")),
            parameter_name=optional_str(value.get("parameter_name"), "parameter_name"),
            metadata_key=optional_str(value.get("metadata_key"), "metadata_key"),
            required=require_bool(value.get("required", True), "required"),
            resolver=optional_str(value.get("resolver"), "resolver"),
            description=optional_str(value.get("description"), "description"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )


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
    external_inputs: tuple[ExternalInputRequirement, ...] = ()
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
        object.__setattr__(self, "external_inputs", _external_input_tuple(self.external_inputs))
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
                "external_inputs": [external_input.to_dict() for external_input in self.external_inputs],
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
            external_inputs=tuple(
                ExternalInputRequirement.from_dict(external_input)
                for external_input in mapping_tuple(value.get("external_inputs"), "external_inputs")
            ),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )


def _external_input_tuple(value: object) -> tuple[ExternalInputRequirement, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise TypeError("external_inputs must be a list of external input requirements")
    requirements: list[ExternalInputRequirement] = []
    for item in value:
        if isinstance(item, ExternalInputRequirement):
            requirements.append(item)
            continue
        if isinstance(item, Mapping):
            requirements.append(ExternalInputRequirement.from_dict(item))
            continue
        raise TypeError("external_inputs must contain only external input requirements")
    return tuple(requirements)
