"""Named pipeline preset helpers for FiftyOne augmentation forms."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike
from typing import Final

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.fixed import (
    build_fixed_pipeline_config,
    validate_fixed_pipeline_config,
)
from albumentationsx_plugin.core import PIPELINE_PRESET_SCHEMA_VERSION, InvalidParameterError, JSONDict, PipelinePreset
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.presets import operator_params_from_pipeline
from albumentationsx_plugin.storage import FilePipelinePresetStore, build_preset_key

PIPELINE_PRESET_KEY_FIELD_NAME: Final[str] = "pipeline_preset_key"
SAVE_PRESET_ONLY_FIELD_NAME: Final[str] = "save_preset_only"
SAVE_PRESET_NAME_FIELD_NAME: Final[str] = "save_preset_name"
SAVE_PRESET_DESCRIPTION_FIELD_NAME: Final[str] = "save_preset_description"
PRESET_SAVED_EXECUTION_STATUS: Final[str] = "preset_saved"


@dataclass(frozen=True, slots=True)
class PipelinePresetSaveResult:
    """Result of saving a named pipeline preset from operator params."""

    preset: PipelinePreset
    preset_path: str

    def to_dict(self) -> JSONDict:
        """Serialize this result using the augmentation operator output shape."""

        return normalize_json_mapping(
            {
                "run_key": "",
                "source_scope": "",
                "processed_count": 0,
                "created_count": 0,
                "skipped_count": 0,
                "error_count": 0,
                "dry_run": False,
                "execution_status": PRESET_SAVED_EXECUTION_STATUS,
                "preview_only": False,
                "output_tag": "",
                "output_dir": "",
                "manifest_path": "",
                "fiftyone_run_key": "",
                "errors": [],
                "preview_count": 0,
                "preset_key": self.preset.key,
                "preset_name": self.preset.name,
                "preset_path": self.preset_path,
            }
        )


def selected_pipeline_preset_key(params: Mapping[str, object]) -> str:
    """Return the selected named preset key, if any."""

    value = params.get(PIPELINE_PRESET_KEY_FIELD_NAME)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def pipeline_preset_save_requested(params: Mapping[str, object]) -> bool:
    """Return whether submitted params contain a named preset to persist."""

    value = params.get(SAVE_PRESET_NAME_FIELD_NAME)
    return isinstance(value, str) and bool(value.strip())


def list_pipeline_presets(
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[PipelinePreset, ...]:
    """Return all shared named presets available to the current plugin environment."""

    return FilePipelinePresetStore(storage_root=storage_root).list_presets()


def params_with_pipeline_preset(
    params: Mapping[str, object],
    *,
    storage_root: str | PathLike[str] | None = None,
) -> dict[str, object]:
    """Overlay a selected named preset's pipeline params over user-provided params."""

    preset_key = selected_pipeline_preset_key(params)
    if not preset_key:
        return dict(params)

    preset = FilePipelinePresetStore(storage_root=storage_root).load_preset(preset_key)
    validate_pipeline_preset(preset)
    return {**params, **operator_params_from_pipeline(preset.pipeline)}


def save_pipeline_preset_from_params(
    params: Mapping[str, object],
    *,
    storage_root: str | PathLike[str] | None = None,
) -> PipelinePresetSaveResult:
    """Validate current operator params and save them as a named shared preset."""

    preset_name = _required_preset_name(params)
    preset_key = build_preset_key(preset_name)
    now = _utc_now()
    store = FilePipelinePresetStore(storage_root=storage_root)
    existing = _load_existing_preset(store, preset_key)
    pipeline = build_fixed_pipeline_config(params)
    validate_fixed_pipeline_config(pipeline)
    preset = PipelinePreset(
        key=preset_key,
        name=preset_name,
        description=_optional_preset_description(params),
        plugin_version=albumentationsx_plugin.__version__,
        dependency_versions={
            "albumentationsx": _dependency_version("albumentationsx"),
            "albu-spec": _dependency_version("albu-spec"),
            "fiftyone": _dependency_version("fiftyone"),
        },
        pipeline=pipeline,
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
        metadata={"source": "fiftyone_augment_form"},
    )
    store.save_preset(preset)
    return PipelinePresetSaveResult(preset=preset, preset_path=str(store.preset_path(preset.key)))


def validate_pipeline_preset(preset: PipelinePreset) -> None:
    """Validate a loaded preset against the current executable catalog."""

    if preset.schema_version != PIPELINE_PRESET_SCHEMA_VERSION:
        raise InvalidParameterError(
            transform_name="<preset>",
            parameter_name="schema_version",
            message="Pipeline preset schema version is not supported.",
            context={
                "schema_version": preset.schema_version,
                "supported_schema_version": PIPELINE_PRESET_SCHEMA_VERSION,
            },
        )
    validate_fixed_pipeline_config(preset.pipeline)


def _load_existing_preset(store: FilePipelinePresetStore, preset_key: str) -> PipelinePreset | None:
    try:
        return store.load_preset(preset_key)
    except Exception:
        return None


def _required_preset_name(params: Mapping[str, object]) -> str:
    value = params.get(SAVE_PRESET_NAME_FIELD_NAME)
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(
            transform_name="<preset>",
            parameter_name=SAVE_PRESET_NAME_FIELD_NAME,
            message="Preset name is required to save a pipeline preset.",
            context={"reason_code": "missing_preset_name"},
        )
    return " ".join(value.split())


def _optional_preset_description(params: Mapping[str, object]) -> str:
    value = params.get(SAVE_PRESET_DESCRIPTION_FIELD_NAME)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "PIPELINE_PRESET_KEY_FIELD_NAME",
    "PRESET_SAVED_EXECUTION_STATUS",
    "SAVE_PRESET_DESCRIPTION_FIELD_NAME",
    "SAVE_PRESET_NAME_FIELD_NAME",
    "SAVE_PRESET_ONLY_FIELD_NAME",
    "PipelinePresetSaveResult",
    "list_pipeline_presets",
    "params_with_pipeline_preset",
    "pipeline_preset_save_requested",
    "save_pipeline_preset_from_params",
    "selected_pipeline_preset_key",
    "validate_pipeline_preset",
]
