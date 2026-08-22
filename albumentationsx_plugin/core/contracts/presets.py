"""Reusable pipeline preset contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, cast

from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig
from albumentationsx_plugin.core.serialization import (
    JSONDict,
    normalize_json_mapping,
    optional_str,
    require_int,
    require_mapping,
    require_str,
    string_tuple,
)

PIPELINE_PRESET_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class PipelinePreset:
    """Named, portable augmentation pipeline template.

    Presets intentionally store reusable pipeline configuration only. They do
    not contain source sample ids, replay records, output paths, or cleanup
    allowlists from materialized runs.
    """

    key: str
    name: str
    pipeline: PipelineConfig
    plugin_version: str
    dependency_versions: Mapping[str, str]
    schema_version: int = PIPELINE_PRESET_SCHEMA_VERSION
    description: str = ""
    tags: tuple[str, ...] = ()
    created_at: str | None = None
    updated_at: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        dependency_versions = dict(self.dependency_versions)
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in dependency_versions.items()):
            raise TypeError("dependency_versions must map strings to strings")
        pipeline = (
            self.pipeline if isinstance(self.pipeline, PipelineConfig) else PipelineConfig.from_dict(self.pipeline)
        )

        object.__setattr__(self, "schema_version", require_int(self.schema_version, "schema_version"))
        object.__setattr__(self, "key", require_str(self.key, "key"))
        object.__setattr__(self, "name", require_str(self.name, "name"))
        object.__setattr__(self, "pipeline", pipeline)
        object.__setattr__(self, "plugin_version", require_str(self.plugin_version, "plugin_version"))
        object.__setattr__(self, "dependency_versions", dependency_versions)
        object.__setattr__(self, "description", _optional_text(self.description, "description"))
        object.__setattr__(self, "tags", string_tuple(self.tags, "tags"))
        object.__setattr__(self, "created_at", optional_str(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", optional_str(self.updated_at, "updated_at"))
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize this preset as the versioned portable JSON schema."""

        return cast(
            JSONDict,
            {
                "schema_version": self.schema_version,
                "key": self.key,
                "name": self.name,
                "description": self.description,
                "tags": list(self.tags),
                "plugin_version": self.plugin_version,
                "dependency_versions": dict(self.dependency_versions),
                "pipeline": self.pipeline.to_dict(),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PipelinePreset:
        """Create a preset from a decoded JSON object."""

        raw_dependency_versions = require_mapping(value.get("dependency_versions", {}), "dependency_versions")
        dependency_versions = {
            require_str(key, "dependency_versions key"): require_str(version, "dependency_versions value")
            for key, version in raw_dependency_versions.items()
        }
        return cls(
            schema_version=require_int(value.get("schema_version", PIPELINE_PRESET_SCHEMA_VERSION), "schema_version"),
            key=require_str(value.get("key"), "key"),
            name=require_str(value.get("name"), "name"),
            description=_optional_text(value.get("description", ""), "description"),
            tags=string_tuple(value.get("tags"), "tags"),
            plugin_version=require_str(value.get("plugin_version"), "plugin_version"),
            dependency_versions=dependency_versions,
            pipeline=PipelineConfig.from_dict(require_mapping(value.get("pipeline"), "pipeline")),
            created_at=optional_str(value.get("created_at"), "created_at"),
            updated_at=optional_str(value.get("updated_at"), "updated_at"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )


__all__ = [
    "PIPELINE_PRESET_SCHEMA_VERSION",
    "PipelinePreset",
]


def _optional_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
