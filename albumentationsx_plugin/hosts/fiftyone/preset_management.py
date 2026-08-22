"""Shared helpers for FiftyOne named preset management actions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from os import PathLike
from typing import Final, cast

from albumentationsx_plugin.core import JSONDict, PipelinePreset
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.dependencies import (
    is_known_runtime_dependency,
    runtime_dependency_package_name,
)
from albumentationsx_plugin.storage import FilePipelinePresetStore, build_preset_key

ACTION_FIELD_NAME: Final[str] = "action"
PRESET_KEY_FIELD_NAME: Final[str] = "preset_key"
PRESET_JSON_FIELD_NAME: Final[str] = "preset_json"
NEW_PRESET_NAME_FIELD_NAME: Final[str] = "new_preset_name"
OVERWRITE_FIELD_NAME: Final[str] = "overwrite"
CONFIRM_DELETE_FIELD_NAME: Final[str] = "confirm_delete"
STORAGE_ROOT_PARAM_NAME: Final[str] = "_storage_root"

ACTION_INSPECT: Final[str] = "inspect"
ACTION_EXPORT: Final[str] = "export"
ACTION_IMPORT: Final[str] = "import"
ACTION_RENAME: Final[str] = "rename"
ACTION_DELETE: Final[str] = "delete"

PRESET_MANAGEMENT_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_INSPECT,
    ACTION_EXPORT,
    ACTION_IMPORT,
    ACTION_RENAME,
    ACTION_DELETE,
)
PRESET_ACTIONS_REQUIRING_PRESET: Final[frozenset[str]] = frozenset(
    {
        ACTION_INSPECT,
        ACTION_EXPORT,
        ACTION_RENAME,
        ACTION_DELETE,
    }
)


@dataclass(frozen=True, slots=True)
class PresetManagementRow:
    """Flat preset summary row for FiftyOne operator output."""

    key: str
    name: str
    description: str
    transform_count: int
    outputs_per_sample: int
    pipeline_summary: str
    plugin_version: str
    created_at: str
    updated_at: str
    path: str

    def to_dict(self) -> JSONDict:
        """Serialize the row to a JSON-compatible mapping."""

        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "transform_count": self.transform_count,
            "outputs_per_sample": self.outputs_per_sample,
            "pipeline_summary": self.pipeline_summary,
            "plugin_version": self.plugin_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class PresetManagementPayload:
    """Result of one preset management action."""

    status: str
    message: str
    action: str
    presets: tuple[PresetManagementRow, ...]
    preset_key: str = ""
    preset_name: str = ""
    preset_path: str = ""
    selected_preset_json: str = ""
    exported_preset_json: str = ""
    errors: tuple[JSONDict, ...] = ()

    def to_dict(self) -> JSONDict:
        """Serialize the action result to FiftyOne operator output."""

        preset_rows = [row.to_dict() for row in self.presets]
        return normalize_json_mapping(
            {
                "status": self.status,
                "message": self.message,
                "action": self.action,
                "preset_key": self.preset_key,
                "preset_name": self.preset_name,
                "preset_path": self.preset_path,
                "preset_count": len(preset_rows),
                "presets": preset_rows,
                "presets_json": json_dump(preset_rows),
                "selected_preset_json": self.selected_preset_json,
                "exported_preset_json": self.exported_preset_json,
                "errors_json": json_dump(list(self.errors)),
            }
        )


def execute_preset_management_action(params: Mapping[str, object]) -> PresetManagementPayload:
    """Execute one preset management action from FiftyOne operator params."""

    action = selected_management_action(params.get(ACTION_FIELD_NAME))
    store = FilePipelinePresetStore(storage_root=storage_root_from_params(params))
    try:
        return _execute_action(store, params=params, action=action)
    except ModuleNotFoundError as error:
        if not is_known_runtime_dependency(error):
            raise
        return error_payload(
            store,
            action=action,
            message=f"Install plugin requirements before importing presets: {runtime_dependency_package_name(error)}.",
            reason="missing_runtime_dependency",
            exception=error,
        )
    except Exception as error:
        return error_payload(
            store,
            action=action,
            message=str(error) or "Preset management action failed.",
            reason=error_reason(error),
            exception=error,
        )


def selected_management_action(raw_value: object) -> str:
    """Return a supported management action, defaulting to inspect."""

    value = string_param(raw_value)
    return value if value in PRESET_MANAGEMENT_ACTIONS else ACTION_INSPECT


def selected_preset_key(raw_value: object, presets: tuple[PipelinePreset, ...]) -> str:
    """Return a selected preset key, defaulting to the first available preset."""

    value = string_param(raw_value)
    preset_keys = tuple(preset.key for preset in presets)
    if value and value in preset_keys:
        return value
    return preset_keys[0] if preset_keys else ""


def storage_root_from_params(params: Mapping[str, object]) -> str | PathLike[str] | None:
    """Return the test-only storage root override from operator params."""

    value = params.get(STORAGE_ROOT_PARAM_NAME)
    if isinstance(value, str):
        return value
    return value if isinstance(value, PathLike) else None


def string_param(value: object) -> str:
    """Return a stripped string param or an empty string."""

    return value.strip() if isinstance(value, str) else ""


def bool_param(value: object) -> bool:
    """Return a boolean param, treating non-bool values as false."""

    return value if isinstance(value, bool) else False


def json_dump(value: object) -> str:
    """Serialize a value as stable formatted JSON."""

    return json.dumps(value, indent=2, sort_keys=True)


def error_reason(error: Exception) -> str:
    """Extract a stable reason code from plugin exceptions where available."""

    context = getattr(error, "context", None)
    if isinstance(context, Mapping):
        reason = context.get("reason") or context.get("reason_code")
        if isinstance(reason, str) and reason:
            return reason
    return "preset_management_failed"


def error_payload(
    store: FilePipelinePresetStore,
    *,
    action: str,
    message: str,
    reason: str,
    preset: PipelinePreset | None = None,
    exception: Exception | None = None,
) -> PresetManagementPayload:
    """Build a non-throwing action error payload."""

    error: JSONDict = {
        "reason": reason,
        "message": message,
    }
    if exception is not None:
        error["exception_type"] = type(exception).__name__
    if preset is not None:
        error["preset_key"] = preset.key
        error["preset_name"] = preset.name

    return PresetManagementPayload(
        status="error",
        message=message,
        action=action,
        presets=preset_rows(store),
        preset_key=preset.key if preset is not None else "",
        preset_name=preset.name if preset is not None else "",
        preset_path=str(store.preset_path(preset.key)) if preset is not None else "",
        errors=(error,),
    )


def preset_rows(store: FilePipelinePresetStore) -> tuple[PresetManagementRow, ...]:
    """Return all readable presets as UI-ready summary rows."""

    rows: list[PresetManagementRow] = []
    for preset in store.list_presets():
        rows.append(
            PresetManagementRow(
                key=preset.key,
                name=preset.name,
                description=preset.description,
                transform_count=len(preset.pipeline.transforms),
                outputs_per_sample=preset.pipeline.outputs_per_sample,
                pipeline_summary=_pipeline_summary(preset),
                plugin_version=preset.plugin_version,
                created_at=preset.created_at or "",
                updated_at=preset.updated_at or "",
                path=str(store.preset_path(preset.key)),
            )
        )
    return tuple(rows)


def _execute_action(
    store: FilePipelinePresetStore,
    *,
    params: Mapping[str, object],
    action: str,
) -> PresetManagementPayload:
    if action == ACTION_INSPECT:
        return _inspect_presets(store, params)
    if action == ACTION_EXPORT:
        return _export_preset(store, params)
    if action == ACTION_IMPORT:
        return _import_preset(store, params)
    if action == ACTION_RENAME:
        return _rename_preset(store, params)
    if action == ACTION_DELETE:
        return _delete_preset(store, params)
    return error_payload(
        store,
        action=action,
        message="Unsupported preset management action.",
        reason="unsupported_action",
    )


def _inspect_presets(
    store: FilePipelinePresetStore,
    params: Mapping[str, object],
) -> PresetManagementPayload:
    presets = store.list_presets()
    selected_key = selected_preset_key(params.get(PRESET_KEY_FIELD_NAME), presets)
    selected = store.load_preset(selected_key) if selected_key else None
    return _success_payload(
        store,
        action=ACTION_INSPECT,
        message=_inspect_message(presets),
        preset=selected,
        selected_preset_json=_preset_json(selected) if selected is not None else "",
    )


def _export_preset(
    store: FilePipelinePresetStore,
    params: Mapping[str, object],
) -> PresetManagementPayload:
    preset = store.load_preset(_required_preset_key(params, store))
    exported_json = _preset_json(preset)
    return _success_payload(
        store,
        action=ACTION_EXPORT,
        message=f"Exported preset '{preset.name}'.",
        preset=preset,
        selected_preset_json=exported_json,
        exported_preset_json=exported_json,
    )


def _import_preset(
    store: FilePipelinePresetStore,
    params: Mapping[str, object],
) -> PresetManagementPayload:
    preset = _preset_from_json_param(params)
    _validate_imported_preset(preset)
    overwrite = bool_param(params.get(OVERWRITE_FIELD_NAME))
    if store.preset_exists(preset.key) and not overwrite:
        return error_payload(
            store,
            action=ACTION_IMPORT,
            message=f"Preset '{preset.key}' already exists. Enable overwrite to replace it.",
            reason="preset_already_exists",
            preset=preset,
        )

    store.save_preset(preset)
    return _success_payload(
        store,
        action=ACTION_IMPORT,
        message=f"Imported preset '{preset.name}'.",
        preset=preset,
        selected_preset_json=_preset_json(preset),
    )


def _rename_preset(
    store: FilePipelinePresetStore,
    params: Mapping[str, object],
) -> PresetManagementPayload:
    preset = store.load_preset(_required_preset_key(params, store))
    new_name = _required_text(params.get(NEW_PRESET_NAME_FIELD_NAME), "New preset name is required.")
    new_key = build_preset_key(new_name)
    overwrite = bool_param(params.get(OVERWRITE_FIELD_NAME))
    if new_key != preset.key and store.preset_exists(new_key) and not overwrite:
        return error_payload(
            store,
            action=ACTION_RENAME,
            message=f"Preset '{new_key}' already exists. Enable overwrite to replace it.",
            reason="preset_already_exists",
            preset=preset,
        )

    metadata = dict(preset.metadata)
    if new_key != preset.key:
        metadata["renamed_from"] = preset.key
    renamed = replace(
        preset,
        key=new_key,
        name=new_name,
        updated_at=_utc_now(),
        metadata=normalize_json_mapping(metadata),
    )
    store.rename_preset(preset.key, renamed, overwrite=overwrite)
    return _success_payload(
        store,
        action=ACTION_RENAME,
        message=f"Renamed preset '{preset.name}' to '{renamed.name}'.",
        preset=renamed,
        selected_preset_json=_preset_json(renamed),
    )


def _delete_preset(
    store: FilePipelinePresetStore,
    params: Mapping[str, object],
) -> PresetManagementPayload:
    preset = store.load_preset(_required_preset_key(params, store))
    if not bool_param(params.get(CONFIRM_DELETE_FIELD_NAME)):
        return error_payload(
            store,
            action=ACTION_DELETE,
            message="Confirm deletion before removing the selected preset.",
            reason="confirmation_required",
            preset=preset,
        )

    preset_path = str(store.preset_path(preset.key))
    store.delete_preset(preset.key)
    return _success_payload(
        store,
        action=ACTION_DELETE,
        message=f"Deleted preset '{preset.name}'.",
        preset=replace(preset, metadata=normalize_json_mapping({"deleted_path": preset_path})),
    )


def _success_payload(
    store: FilePipelinePresetStore,
    *,
    action: str,
    message: str,
    preset: PipelinePreset | None = None,
    selected_preset_json: str = "",
    exported_preset_json: str = "",
) -> PresetManagementPayload:
    return PresetManagementPayload(
        status="ok",
        message=message,
        action=action,
        presets=preset_rows(store),
        preset_key=preset.key if preset is not None else "",
        preset_name=preset.name if preset is not None else "",
        preset_path=str(store.preset_path(preset.key)) if preset is not None else "",
        selected_preset_json=selected_preset_json,
        exported_preset_json=exported_preset_json,
    )


def _preset_from_json_param(params: Mapping[str, object]) -> PipelinePreset:
    raw_json = _required_text(params.get(PRESET_JSON_FIELD_NAME), "Preset JSON is required.")
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise ValueError("Preset JSON could not be parsed.") from error
    if not isinstance(payload, Mapping):
        raise TypeError("Preset JSON must be an object.")
    preset = PipelinePreset.from_dict(cast(Mapping[str, object], payload))
    expected_key = build_preset_key(preset.name)
    if preset.key != expected_key:
        raise ValueError("Preset key must match the normalized preset name.")
    return preset


def _validate_imported_preset(preset: PipelinePreset) -> None:
    from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import validate_pipeline_preset

    validate_pipeline_preset(preset)


def _required_preset_key(params: Mapping[str, object], store: FilePipelinePresetStore) -> str:
    preset_key = string_param(params.get(PRESET_KEY_FIELD_NAME))
    if preset_key:
        return preset_key
    preset_keys = store.list_preset_keys()
    if preset_keys:
        return preset_keys[0]
    raise ValueError("A preset must be selected for this action.")


def _pipeline_summary(preset: PipelinePreset) -> str:
    labels: list[str] = []
    for transform in preset.pipeline.transforms:
        if transform.params:
            params = ", ".join(f"{key}={value!r}" for key, value in sorted(transform.params.items()))
            labels.append(f"{transform.name}({params})")
        else:
            labels.append(transform.name)
    return " -> ".join(labels)


def _preset_json(preset: PipelinePreset | None) -> str:
    return json_dump(preset.to_dict()) if preset is not None else ""


def _inspect_message(presets: tuple[PipelinePreset, ...]) -> str:
    count = len(presets)
    if count == 1:
        return "Found 1 named preset."
    return f"Found {count} named presets."


def _required_text(raw_value: object, message: str) -> str:
    value = string_param(raw_value)
    if not value:
        raise ValueError(message)
    return " ".join(value.split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
