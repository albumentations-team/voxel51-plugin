"""Host-neutral form schema contracts.

The Albumentations backend produces these schemas from albu-spec metadata.
FiftyOne, or any future host, renders them into its own UI components.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from albumentationsx_plugin.core.serialization import (
    JSONDict,
    JSONValue,
    normalize_json_mapping,
    normalize_json_value,
    optional_float,
    optional_str,
    require_bool,
    require_mapping,
    require_str,
)


class FieldKind(StrEnum):
    """Host-neutral field kinds that can be rendered by a UI adapter."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"
    NUMBER_RANGE = "number_range"
    LIST = "list"
    OBJECT = "object"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class FormFieldSchema:
    """Schema for one form field before it is mapped to host-specific UI.

    Nested fields are represented through `properties`. List item definitions
    can use `item_schema` until the concrete renderer has richer typed helpers.
    """

    name: str
    kind: FieldKind
    label: str | None = None
    required: bool = False
    default: JSONValue = None
    min_value: float | None = None
    max_value: float | None = None
    choices: tuple[JSONValue, ...] = ()
    item_schema: Mapping[str, object] | None = None
    properties: tuple[FormFieldSchema, ...] = ()
    help_text: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_str(self.name, "name"))
        object.__setattr__(self, "kind", FieldKind(self.kind))
        object.__setattr__(self, "label", optional_str(self.label, "label"))
        object.__setattr__(self, "default", normalize_json_value(self.default))
        object.__setattr__(self, "min_value", optional_float(self.min_value, "min_value"))
        object.__setattr__(self, "max_value", optional_float(self.max_value, "max_value"))
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value cannot be greater than max_value")
        if not isinstance(self.required, bool):
            raise TypeError("required must be a boolean")

        choices = tuple(normalize_json_value(choice) for choice in self.choices)
        object.__setattr__(self, "choices", choices)
        if self.kind == FieldKind.ENUM and not choices:
            raise ValueError("enum fields must define choices")
        object.__setattr__(
            self,
            "item_schema",
            None if self.item_schema is None else normalize_json_mapping(self.item_schema),
        )
        object.__setattr__(
            self,
            "properties",
            tuple(
                prop if isinstance(prop, FormFieldSchema) else FormFieldSchema.from_dict(require_mapping(prop, "prop"))
                for prop in self.properties
            ),
        )
        object.__setattr__(self, "help_text", optional_str(self.help_text, "help_text"))
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the field schema for snapshots or host payloads."""

        return cast(
            JSONDict,
            {
                "name": self.name,
                "kind": self.kind.value,
                "label": self.label,
                "required": self.required,
                "default": normalize_json_value(self.default),
                "min_value": self.min_value,
                "max_value": self.max_value,
                "choices": [normalize_json_value(choice) for choice in self.choices],
                "item_schema": None if self.item_schema is None else normalize_json_mapping(self.item_schema),
                "properties": [prop.to_dict() for prop in self.properties],
                "help_text": self.help_text,
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> FormFieldSchema:
        """Create a field schema from a decoded JSON object."""

        raw_properties = value.get("properties", [])
        if not isinstance(raw_properties, list | tuple):
            raise TypeError("properties must be a list")
        raw_choices = value.get("choices", [])
        if not isinstance(raw_choices, list | tuple):
            raise TypeError("choices must be a list")
        raw_item_schema = value.get("item_schema")
        item_schema = None if raw_item_schema is None else require_mapping(raw_item_schema, "item_schema")
        return cls(
            name=require_str(value.get("name"), "name"),
            kind=FieldKind(require_str(value.get("kind"), "kind")),
            label=optional_str(value.get("label"), "label"),
            required=require_bool(value.get("required", False), "required"),
            default=normalize_json_value(value.get("default")),
            min_value=optional_float(value.get("min_value"), "min_value"),
            max_value=optional_float(value.get("max_value"), "max_value"),
            choices=tuple(normalize_json_value(choice) for choice in raw_choices),
            item_schema=None if item_schema is None else normalize_json_mapping(item_schema),
            properties=tuple(FormFieldSchema.from_dict(require_mapping(prop, "property")) for prop in raw_properties),
            help_text=optional_str(value.get("help_text"), "help_text"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )
