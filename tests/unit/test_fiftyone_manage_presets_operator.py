from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.preset_management as preset_management_module
from albumentationsx_plugin.core import PipelineConfig, PipelinePreset, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.operators.manage_presets import (
    ACTION_DELETE,
    ACTION_EXPORT,
    ACTION_FIELD_NAME,
    ACTION_IMPORT,
    ACTION_RENAME,
    CONFIRM_DELETE_FIELD_NAME,
    NEW_PRESET_NAME_FIELD_NAME,
    OPERATOR_NAME,
    OVERWRITE_FIELD_NAME,
    PRESET_JSON_FIELD_NAME,
    PRESET_KEY_FIELD_NAME,
    PRESET_STORAGE_WARNING_FIELD_NAME,
    STORAGE_ROOT_PARAM_NAME,
    ManageAlbumentationsXPresets,
)
from albumentationsx_plugin.storage import FilePipelinePresetStore, build_preset_key

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


@pytest.mark.unit
def test_manage_presets_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = ManageAlbumentationsXPresets()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Manage AlbumentationsX Presets"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "high"


@pytest.mark.unit
def test_manage_presets_operator_resolves_export_form_and_output(tmp_path) -> None:
    preset = _save_preset(tmp_path, "Training defaults")
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_EXPORT,
            PRESET_KEY_FIELD_NAME: preset.key,
        }

    input_json = operator.resolve_input(Context()).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]

    assert input_json["view"]["label"] == "Manage AlbumentationsX Presets"
    assert input_json["view"]["submit_button_label"] == "Export preset"
    assert input_properties["action"]["type"]["name"] == "Enum"
    assert input_properties["action"]["default"] == ACTION_EXPORT
    assert input_properties["preset_key"]["type"]["name"] == "Enum"
    assert input_properties["preset_key"]["default"] == preset.key
    assert output_properties["presets"]["type"]["name"] == "List"
    assert output_properties["exported_preset_json"]["type"]["name"] == "String"
    assert output_properties["errors_json"]["type"]["name"] == "String"


@pytest.mark.unit
def test_manage_presets_operator_resolves_import_form(tmp_path) -> None:
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_IMPORT,
            PRESET_JSON_FIELD_NAME: "{}",
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_json["view"]["submit_button_label"] == "Import preset"
    assert input_properties["preset_json"]["type"]["name"] == "String"
    assert input_properties["overwrite"]["type"]["name"] == "Boolean"
    assert "preset_key" not in input_properties


@pytest.mark.unit
def test_manage_presets_operator_resolves_form_when_preset_storage_cannot_be_listed(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_EXPORT,
        }

    def broken_list_presets(self: FilePipelinePresetStore) -> tuple[PipelinePreset, ...]:
        raise RuntimeError("preset directory is not readable")

    monkeypatch.setattr(FilePipelinePresetStore, "list_presets", broken_list_presets)
    caplog.set_level(logging.DEBUG, logger="albumentationsx_plugin.hosts.fiftyone.operators.manage_presets")

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties[PRESET_STORAGE_WARNING_FIELD_NAME]["view"]["label"] == "Preset storage"
    assert "RuntimeError" in input_properties[PRESET_STORAGE_WARNING_FIELD_NAME]["view"]["description"]
    assert input_properties[PRESET_KEY_FIELD_NAME]["type"]["name"] == "String"
    assert "No named AlbumentationsX presets" in input_properties[PRESET_KEY_FIELD_NAME]["view"]["description"]
    assert "Error while listing pipeline presets" in caplog.text


@pytest.mark.unit
def test_manage_presets_operator_exports_preset_json(tmp_path) -> None:
    preset = _save_preset(tmp_path, "Training defaults")
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_EXPORT,
            PRESET_KEY_FIELD_NAME: preset.key,
        }

    result = operator.execute(Context())

    assert result["status"] == "ok"
    assert result["action"] == ACTION_EXPORT
    assert result["preset_key"] == preset.key
    assert json.loads(str(result["exported_preset_json"])) == preset.to_dict()
    assert json.loads(str(result["presets_json"]))[0]["key"] == preset.key


@pytest.mark.unit
def test_manage_presets_operator_imports_valid_preset_json(tmp_path, monkeypatch) -> None:
    preset = _preset("Imported defaults")
    operator = ManageAlbumentationsXPresets()
    validated: list[PipelinePreset] = []

    monkeypatch.setattr(preset_management_module, "_validate_imported_preset", validated.append)

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_IMPORT,
            PRESET_JSON_FIELD_NAME: json.dumps(preset.to_dict()),
        }

    result = operator.execute(Context())
    store = FilePipelinePresetStore(storage_root=tmp_path)

    assert result["status"] == "ok"
    assert result["preset_key"] == preset.key
    assert store.load_preset(preset.key) == preset
    assert validated == [preset]


@pytest.mark.unit
def test_manage_presets_operator_rejects_import_overwrite_without_confirmation(tmp_path, monkeypatch) -> None:
    preset = _save_preset(tmp_path, "Imported defaults")
    operator = ManageAlbumentationsXPresets()
    monkeypatch.setattr(preset_management_module, "_validate_imported_preset", lambda preset: None)

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_IMPORT,
            PRESET_JSON_FIELD_NAME: json.dumps(preset.to_dict()),
            OVERWRITE_FIELD_NAME: False,
        }

    result = operator.execute(Context())

    assert result["status"] == "error"
    assert result["preset_key"] == preset.key
    assert json.loads(str(result["errors_json"]))[0]["reason"] == "preset_already_exists"


@pytest.mark.unit
def test_manage_presets_operator_renames_preset_and_removes_old_file(tmp_path) -> None:
    preset = _save_preset(tmp_path, "Training defaults")
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_RENAME,
            PRESET_KEY_FIELD_NAME: preset.key,
            NEW_PRESET_NAME_FIELD_NAME: "Validation defaults",
        }

    result = operator.execute(Context())
    store = FilePipelinePresetStore(storage_root=tmp_path)
    renamed_key = build_preset_key("Validation defaults")
    renamed = store.load_preset(renamed_key)

    assert result["status"] == "ok"
    assert result["preset_key"] == renamed_key
    assert not store.preset_exists(preset.key)
    assert renamed.name == "Validation defaults"
    assert renamed.pipeline == preset.pipeline
    assert renamed.created_at == preset.created_at
    assert renamed.updated_at is not None
    assert renamed.metadata["renamed_from"] == preset.key


@pytest.mark.unit
def test_manage_presets_operator_requires_delete_confirmation(tmp_path) -> None:
    preset = _save_preset(tmp_path, "Training defaults")
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_DELETE,
            PRESET_KEY_FIELD_NAME: preset.key,
            CONFIRM_DELETE_FIELD_NAME: False,
        }

    result = operator.execute(Context())

    assert result["status"] == "error"
    assert FilePipelinePresetStore(storage_root=tmp_path).preset_exists(preset.key)
    assert json.loads(str(result["errors_json"]))[0]["reason"] == "confirmation_required"


@pytest.mark.unit
def test_manage_presets_operator_deletes_confirmed_preset_only(tmp_path) -> None:
    preset = _save_preset(tmp_path, "Training defaults")
    operator = ManageAlbumentationsXPresets()

    class Context:
        params = {
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            ACTION_FIELD_NAME: ACTION_DELETE,
            PRESET_KEY_FIELD_NAME: preset.key,
            CONFIRM_DELETE_FIELD_NAME: True,
        }

    result = operator.execute(Context())

    assert result["status"] == "ok"
    assert result["preset_key"] == preset.key
    assert result["preset_count"] == 0
    assert not FilePipelinePresetStore(storage_root=tmp_path).preset_exists(preset.key)


def _save_preset(storage_root: pathlib.Path, name: str) -> PipelinePreset:
    preset = _preset(name)
    FilePipelinePresetStore(storage_root=storage_root).save_preset(preset)
    return preset


def _preset(name: str) -> PipelinePreset:
    return PipelinePreset(
        key=build_preset_key(name),
        name=name,
        description=f"{name} description",
        plugin_version="0.1.0",
        dependency_versions={"fiftyone": "1.19.0", "albumentationsx": "2.3.8", "albu-spec": "0.0.6"},
        pipeline=PipelineConfig(
            transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),),
            outputs_per_sample=2,
        ),
        created_at="2026-08-01T00:00:00Z",
        updated_at="2026-08-01T01:00:00Z",
    )
