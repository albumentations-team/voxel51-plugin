"""Saved pipeline helpers for FiftyOne augmentation forms."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from os import PathLike
from typing import Any, Final

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.image_pipeline import validate_fixed_pipeline_config
from albumentationsx_plugin.core import PIPELINE_PRESET_SCHEMA_VERSION, InvalidParameterError, JSONDict, PipelinePreset
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    selected_annotation_fields_from_params,
    target_and_copy_fields,
    validate_annotation_pipeline_compatibility,
    validate_selected_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import build_fixed_pipeline_config
from albumentationsx_plugin.storage import FilePipelinePresetStore, new_preset_key

PIPELINE_PRESET_KEY_FIELD_NAME: Final[str] = "pipeline_preset_key"
SAVE_PRESET_ONLY_FIELD_NAME: Final[str] = "save_preset_only"
SAVE_PRESET_NAME_FIELD_NAME: Final[str] = "save_preset_name"
SAVE_PRESET_DESCRIPTION_FIELD_NAME: Final[str] = "save_preset_description"
SAVE_PRESET_MODE_FIELD_NAME: Final[str] = "save_preset_mode"
SAVE_PRESET_TARGET_FIELD_NAME: Final[str] = "save_preset_target"
SAVE_PRESET_CONFIRM_FIELD_NAME: Final[str] = "save_preset_confirm_update"
PRESET_SAVED_EXECUTION_STATUS: Final[str] = "preset_saved"


@dataclass(frozen=True, slots=True)
class PipelinePresetSaveResult:
    """Result of saving a saved pipeline from operator params."""

    preset: PipelinePreset
    preset_path: str
    updated: bool = False

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
                "preset_save_action": "updated" if self.updated else "created",
            }
        )


def selected_pipeline_preset_key(params: Mapping[str, object]) -> str:
    """Return the selected saved pipeline key, if any."""

    value = params.get(PIPELINE_PRESET_KEY_FIELD_NAME)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def pipeline_preset_save_requested(params: Mapping[str, object]) -> bool:
    """Return whether submitted params contain a saved pipeline to persist."""

    value = params.get(SAVE_PRESET_NAME_FIELD_NAME)
    return isinstance(value, str) and bool(value.strip())


def list_pipeline_presets(
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[PipelinePreset, ...]:
    """Return all shared saved pipelines available to the current plugin environment."""

    return FilePipelinePresetStore(storage_root=storage_root).list_presets()


def save_pipeline_preset_from_params(
    params: Mapping[str, object],
    *,
    dataset: Any = None,
    storage_root: str | PathLike[str] | None = None,
) -> PipelinePresetSaveResult:
    """Validate current operator params and save them as a named shared saved pipeline."""

    preset_name = _required_preset_name(params)
    now = _utc_now()
    store = FilePipelinePresetStore(storage_root=storage_root)
    existing = preset_update_target(params, store)
    preset_key = existing.key if existing is not None else new_preset_key()
    pipeline = build_fixed_pipeline_config(params)
    metadata: dict[str, object] = dict(existing.metadata) if existing else {}
    metadata["source"] = "fiftyone_augment_form"
    if dataset is not None:
        selection = selected_annotation_fields_from_params(params, dataset)
        validate_selected_annotation_fields(selection)
        validate_annotation_pipeline_compatibility(
            selection=selection, pipeline=pipeline, catalog_provider=AlbuSpecCatalogProvider()
        )
        target_fields, copy_fields = target_and_copy_fields(
            selection=selection, pipeline=pipeline, catalog_provider=AlbuSpecCatalogProvider()
        )
        pipeline = replace(pipeline, target_fields=target_fields, copy_fields=copy_fields)
        metadata["annotation_selection"] = {
            "source_dataset": getattr(dataset, "name", None),
            "selected_fields": [field.to_dict() for field in selection.selected_fields],
        }
    validate_fixed_pipeline_config(pipeline)
    preset = PipelinePreset(
        key=preset_key,
        name=preset_name,
        description=_optional_preset_description(params),
        tags=existing.tags if existing is not None else (),
        plugin_version=albumentationsx_plugin.__version__,
        dependency_versions={
            "albumentationsx": _dependency_version("albumentationsx"),
            "albu-spec": _dependency_version("albu-spec"),
            "fiftyone": _dependency_version("fiftyone"),
        },
        pipeline=pipeline,
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
        metadata=metadata,
    )
    store.save_preset(preset, overwrite=existing is not None)
    return PipelinePresetSaveResult(
        preset=preset, preset_path=str(store.preset_path(preset.key)), updated=existing is not None
    )


def validate_pipeline_preset(preset: PipelinePreset) -> None:
    """Validate a loaded saved pipeline against the current executable catalog."""

    if preset.schema_version != PIPELINE_PRESET_SCHEMA_VERSION:
        raise InvalidParameterError(
            transform_name="<preset>",
            parameter_name="schema_version",
            message="Saved pipeline schema version is not supported.",
            context={
                "schema_version": preset.schema_version,
                "supported_schema_version": PIPELINE_PRESET_SCHEMA_VERSION,
            },
        )
    validate_fixed_pipeline_config(preset.pipeline)


def preset_update_target(params: Mapping[str, object], store: FilePipelinePresetStore) -> PipelinePreset | None:
    """Resolve only an explicitly selected and confirmed replacement target."""
    mode = params.get(SAVE_PRESET_MODE_FIELD_NAME, "new")
    if mode == "new":
        return None
    if mode != "update":
        raise _save_error(
            SAVE_PRESET_MODE_FIELD_NAME, "invalid_save_mode", "Choose Save as new or Update existing pipeline."
        )
    target = params.get(SAVE_PRESET_TARGET_FIELD_NAME)
    if not isinstance(target, str) or not target:
        raise _save_error(
            SAVE_PRESET_TARGET_FIELD_NAME, "missing_update_target", "Select the saved pipeline to update."
        )
    existing = store.load_preset(target)
    confirmations = params.get(SAVE_PRESET_CONFIRM_FIELD_NAME)
    if not isinstance(confirmations, Mapping) or confirmations.get(existing.key) is not True:
        raise _save_error(
            SAVE_PRESET_CONFIRM_FIELD_NAME,
            "confirmation_required",
            f"Confirm replacement of '{existing.name}' ({existing.key}) or choose Save as new pipeline.",
        )
    return existing


def _save_error(field: str, reason: str, message: str) -> InvalidParameterError:
    return InvalidParameterError(
        transform_name="<preset>", parameter_name=field, message=message, context={"reason_code": reason}
    )


def _required_preset_name(params: Mapping[str, object]) -> str:
    value = params.get(SAVE_PRESET_NAME_FIELD_NAME)
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(
            transform_name="<preset>",
            parameter_name=SAVE_PRESET_NAME_FIELD_NAME,
            message="Enter a name before saving the pipeline.",
            context={"reason_code": "missing_preset_name"},
        )
    return value.strip()


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
    "pipeline_preset_save_requested",
    "save_pipeline_preset_from_params",
    "selected_pipeline_preset_key",
    "validate_pipeline_preset",
]
