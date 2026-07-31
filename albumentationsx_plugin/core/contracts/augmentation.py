"""Host-neutral augmentation input and result contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from albumentationsx_plugin.core.serialization import (
    JSONDict,
    mapping_tuple,
    normalize_json_mapping,
    optional_str,
    require_int,
    require_mapping,
    require_str,
    string_tuple,
)


@dataclass(frozen=True, slots=True)
class AugmentationInput:
    """Source media item prepared by a host adapter.

    Host adapters may keep host-specific details in `metadata`, but the values
    must remain JSON-serializable so they can be persisted with run results.
    """

    sample_id: str
    filepath: str
    media_type: str = "image"
    width: int | None = None
    height: int | None = None
    selected_label_fields: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_id", require_str(self.sample_id, "sample_id"))
        object.__setattr__(self, "filepath", require_str(self.filepath, "filepath"))
        object.__setattr__(self, "media_type", require_str(self.media_type, "media_type"))
        if self.width is not None and require_int(self.width, "width") < 1:
            raise ValueError("width must be at least 1")
        if self.height is not None and require_int(self.height, "height") < 1:
            raise ValueError("height must be at least 1")
        object.__setattr__(
            self,
            "selected_label_fields",
            string_tuple(self.selected_label_fields, "selected_label_fields"),
        )
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the source input for debugging or manifests."""

        return cast(
            JSONDict,
            {
                "sample_id": self.sample_id,
                "filepath": self.filepath,
                "media_type": self.media_type,
                "width": self.width,
                "height": self.height,
                "selected_label_fields": list(self.selected_label_fields),
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> AugmentationInput:
        """Create an augmentation input from a decoded JSON object."""

        raw_width = value.get("width")
        raw_height = value.get("height")
        return cls(
            sample_id=require_str(value.get("sample_id"), "sample_id"),
            filepath=require_str(value.get("filepath"), "filepath"),
            media_type=require_str(value.get("media_type", "image"), "media_type"),
            width=None if raw_width is None else require_int(raw_width, "width"),
            height=None if raw_height is None else require_int(raw_height, "height"),
            selected_label_fields=string_tuple(value.get("selected_label_fields"), "selected_label_fields"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )


@dataclass(frozen=True, slots=True)
class AugmentationResult:
    """Result of applying a pipeline to one source media item."""

    source_sample_id: str
    output_filepath: str | None = None
    labels: Mapping[str, object] = field(default_factory=dict)
    replay: Mapping[str, object] = field(default_factory=dict)
    errors: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_sample_id", require_str(self.source_sample_id, "source_sample_id"))
        object.__setattr__(self, "output_filepath", optional_str(self.output_filepath, "output_filepath"))
        object.__setattr__(self, "labels", normalize_json_mapping(self.labels))
        object.__setattr__(self, "replay", normalize_json_mapping(self.replay))
        object.__setattr__(self, "errors", mapping_tuple(self.errors, "errors"))
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the result for host adapters and run manifests."""

        return cast(
            JSONDict,
            {
                "source_sample_id": self.source_sample_id,
                "output_filepath": self.output_filepath,
                "labels": normalize_json_mapping(self.labels),
                "replay": normalize_json_mapping(self.replay),
                "errors": [normalize_json_mapping(error) for error in self.errors],
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> AugmentationResult:
        """Create an augmentation result from a decoded JSON object."""

        return cls(
            source_sample_id=require_str(value.get("source_sample_id"), "source_sample_id"),
            output_filepath=optional_str(value.get("output_filepath"), "output_filepath"),
            labels=normalize_json_mapping(require_mapping(value.get("labels", {}), "labels")),
            replay=normalize_json_mapping(require_mapping(value.get("replay", {}), "replay")),
            errors=mapping_tuple(value.get("errors"), "errors"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )
