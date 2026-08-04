"""Pipeline configuration contracts.

These DTOs describe the user's requested augmentation pipeline without creating
AlbumentationsX runtime objects. The backend factory is responsible for turning
the validated names and JSON parameters into concrete transforms.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from albumentationsx_plugin.core.serialization import (
    JSONDict,
    normalize_json_mapping,
    require_bool,
    require_int,
    require_mapping,
    require_str,
    string_tuple,
)


@dataclass(frozen=True, slots=True)
class TransformConfig:
    """One transform name and its JSON-serializable constructor parameters."""

    name: str
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_str(self.name, "name"))
        object.__setattr__(self, "params", normalize_json_mapping(self.params))

    def to_dict(self) -> JSONDict:
        """Serialize the transform config for manifests or operator payloads."""

        return cast(
            JSONDict,
            {
                "name": self.name,
                "params": normalize_json_mapping(self.params),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TransformConfig:
        """Create a transform config from a decoded JSON object."""

        return cls(
            name=require_str(value.get("name"), "name"),
            params=normalize_json_mapping(require_mapping(value.get("params", {}), "params")),
        )


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Ordered transform pipeline plus execution options.

    `target_fields` are label fields that should be transformed in sync with the
    image. `copy_fields` are non-spatial fields that may be copied unchanged.
    """

    transforms: tuple[TransformConfig, ...]
    outputs_per_sample: int = 1
    target_fields: tuple[str, ...] = ()
    copy_fields: tuple[str, ...] = ()
    use_replay: bool = True
    seed: int | None = None
    options: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        transforms = tuple(
            transform if isinstance(transform, TransformConfig) else TransformConfig.from_dict(transform)
            for transform in self.transforms
        )
        outputs_per_sample = require_int(self.outputs_per_sample, "outputs_per_sample")
        if outputs_per_sample < 1:
            raise ValueError("outputs_per_sample must be at least 1")
        if self.seed is not None:
            require_int(self.seed, "seed")
        if not isinstance(self.use_replay, bool):
            raise TypeError("use_replay must be a boolean")

        object.__setattr__(self, "transforms", transforms)
        object.__setattr__(self, "outputs_per_sample", outputs_per_sample)
        object.__setattr__(self, "target_fields", string_tuple(self.target_fields, "target_fields"))
        object.__setattr__(self, "copy_fields", string_tuple(self.copy_fields, "copy_fields"))
        object.__setattr__(self, "options", normalize_json_mapping(self.options))

    def to_dict(self) -> JSONDict:
        """Serialize the pipeline config for persistence and UI exchange."""

        return cast(
            JSONDict,
            {
                "transforms": [transform.to_dict() for transform in self.transforms],
                "outputs_per_sample": self.outputs_per_sample,
                "target_fields": list(self.target_fields),
                "copy_fields": list(self.copy_fields),
                "use_replay": self.use_replay,
                "seed": self.seed,
                "options": normalize_json_mapping(self.options),
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PipelineConfig:
        """Create a pipeline config from a decoded JSON object."""

        raw_transforms = value.get("transforms", [])
        if not isinstance(raw_transforms, list | tuple):
            raise TypeError("transforms must be a list")
        raw_seed = value.get("seed")
        return cls(
            transforms=tuple(TransformConfig.from_dict(require_mapping(item, "transform")) for item in raw_transforms),
            outputs_per_sample=require_int(value.get("outputs_per_sample", 1), "outputs_per_sample"),
            target_fields=string_tuple(value.get("target_fields"), "target_fields"),
            copy_fields=string_tuple(value.get("copy_fields"), "copy_fields"),
            use_replay=require_bool(value.get("use_replay", True), "use_replay"),
            seed=None if raw_seed is None else require_int(raw_seed, "seed"),
            options=normalize_json_mapping(require_mapping(value.get("options", {}), "options")),
        )
