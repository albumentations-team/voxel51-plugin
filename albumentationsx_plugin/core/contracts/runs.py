"""Run manifest contract for persistence and cleanup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from albumentationsx_plugin.core.contracts.pipeline import PipelineConfig
from albumentationsx_plugin.core.serialization import (
    JSONDict,
    mapping_tuple,
    normalize_json_mapping,
    require_int,
    require_mapping,
    require_str,
    string_tuple,
)


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Persisted description of one plugin-created augmentation run.

    The manifest is the cleanup allowlist. File paths should be relative to the
    plugin-owned run directory so later cleanup can prove containment before any
    destructive operation.
    """

    run_key: str
    plugin_version: str
    dependency_versions: Mapping[str, str]
    pipeline: PipelineConfig
    source_sample_ids: tuple[str, ...] = ()
    created_sample_ids: tuple[str, ...] = ()
    output_paths: tuple[str, ...] = ()
    replay_records: tuple[Mapping[str, object], ...] = ()
    counters: Mapping[str, int] = field(default_factory=dict)
    errors: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        dependency_versions = dict(self.dependency_versions)
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in dependency_versions.items()):
            raise TypeError("dependency_versions must map strings to strings")
        counters = dict(self.counters)
        if not all(isinstance(key, str) and isinstance(value, int) for key, value in counters.items()):
            raise TypeError("counters must map strings to integers")

        pipeline = (
            self.pipeline if isinstance(self.pipeline, PipelineConfig) else PipelineConfig.from_dict(self.pipeline)
        )

        object.__setattr__(self, "run_key", require_str(self.run_key, "run_key"))
        object.__setattr__(self, "plugin_version", require_str(self.plugin_version, "plugin_version"))
        object.__setattr__(self, "dependency_versions", dependency_versions)
        object.__setattr__(self, "pipeline", pipeline)
        object.__setattr__(self, "source_sample_ids", string_tuple(self.source_sample_ids, "source_sample_ids"))
        object.__setattr__(self, "created_sample_ids", string_tuple(self.created_sample_ids, "created_sample_ids"))
        object.__setattr__(self, "output_paths", string_tuple(self.output_paths, "output_paths"))
        object.__setattr__(self, "replay_records", mapping_tuple(self.replay_records, "replay_records"))
        object.__setattr__(self, "counters", counters)
        object.__setattr__(self, "errors", mapping_tuple(self.errors, "errors"))
        object.__setattr__(self, "metadata", normalize_json_mapping(self.metadata))

    def to_dict(self) -> JSONDict:
        """Serialize the manifest for `manifest.json` or FiftyOne custom runs."""

        return cast(
            JSONDict,
            {
                "run_key": self.run_key,
                "plugin_version": self.plugin_version,
                "dependency_versions": dict(self.dependency_versions),
                "pipeline": self.pipeline.to_dict(),
                "source_sample_ids": list(self.source_sample_ids),
                "created_sample_ids": list(self.created_sample_ids),
                "output_paths": list(self.output_paths),
                "replay_records": [normalize_json_mapping(record) for record in self.replay_records],
                "counters": dict(self.counters),
                "errors": [normalize_json_mapping(error) for error in self.errors],
                "metadata": normalize_json_mapping(self.metadata),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> RunManifest:
        """Create a run manifest from a decoded JSON object."""

        raw_pipeline = require_mapping(value.get("pipeline"), "pipeline")
        raw_dependency_versions = require_mapping(value.get("dependency_versions", {}), "dependency_versions")
        dependency_versions = {
            require_str(key, "dependency_versions key"): require_str(version, "dependency_versions value")
            for key, version in raw_dependency_versions.items()
        }
        raw_counters = require_mapping(value.get("counters", {}), "counters")
        counters = {
            require_str(key, "counter key"): require_int(counter, "counter value")
            for key, counter in raw_counters.items()
        }
        return cls(
            run_key=require_str(value.get("run_key"), "run_key"),
            plugin_version=require_str(value.get("plugin_version"), "plugin_version"),
            dependency_versions=dependency_versions,
            pipeline=PipelineConfig.from_dict(raw_pipeline),
            source_sample_ids=string_tuple(value.get("source_sample_ids"), "source_sample_ids"),
            created_sample_ids=string_tuple(value.get("created_sample_ids"), "created_sample_ids"),
            output_paths=string_tuple(value.get("output_paths"), "output_paths"),
            replay_records=mapping_tuple(value.get("replay_records"), "replay_records"),
            counters=counters,
            errors=mapping_tuple(value.get("errors"), "errors"),
            metadata=normalize_json_mapping(require_mapping(value.get("metadata", {}), "metadata")),
        )
