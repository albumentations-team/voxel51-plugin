from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.delete_run as delete_run_operator_module
from albumentationsx_plugin.hosts.fiftyone.operators.delete_run import (
    CONFIRM_FIELD_NAME,
    OPERATOR_NAME,
    STORAGE_ROOT_PARAM_NAME,
    DeleteAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.run_cleanup import RunCleanupResult

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


@pytest.mark.unit
def test_delete_run_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = DeleteAlbumentationsXRun()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Delete AlbumentationsX Run"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "high"


@pytest.mark.unit
def test_delete_run_operator_resolves_run_selector_confirmation_and_output(monkeypatch) -> None:
    operator = DeleteAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {}

    def fake_list_available_run_keys(dataset: object, **kwargs) -> tuple[str, ...]:
        assert dataset is Context.dataset
        assert kwargs["storage_root"] is None
        return ("albumentationsx-20260731T150000Z-first",)

    monkeypatch.setattr(delete_run_operator_module, "list_available_run_keys", fake_list_available_run_keys)

    input_json = operator.resolve_input(Context()).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]

    assert input_json["view"]["label"] == "Delete AlbumentationsX Run"
    assert input_properties["run_key"]["type"]["name"] == "Enum"
    assert input_properties["run_key"]["default"] == "albumentationsx-20260731T150000Z-first"
    assert input_properties["run_key"]["view"]["name"] == "AutocompleteView"
    assert input_properties[CONFIRM_FIELD_NAME]["type"]["name"] == "Boolean"
    assert input_properties[CONFIRM_FIELD_NAME]["default"] is False
    assert "Delete generated samples" in input_properties[CONFIRM_FIELD_NAME]["view"]["description"]
    assert output_properties["deleted_sample_count"]["type"]["name"] == "Number"
    assert output_properties["custom_run_deleted"]["type"]["name"] == "Boolean"
    assert output_properties["errors_json"]["type"]["name"] == "String"


@pytest.mark.unit
def test_delete_run_operator_resolves_samples_grid_placement() -> None:
    operator = DeleteAlbumentationsXRun()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "Delete AlbumentationsX Run"


@pytest.mark.unit
def test_delete_run_operator_execute_delegates_to_cleanup_service(monkeypatch) -> None:
    operator = DeleteAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {
            "run_key": "albumentationsx-20260731T150000Z-run",
            CONFIRM_FIELD_NAME: True,
            STORAGE_ROOT_PARAM_NAME: "/tmp/plugin-storage",
        }

    def fake_cleanup_run(dataset: object, run_key: str, **kwargs) -> RunCleanupResult:
        assert dataset is Context.dataset
        assert run_key == "albumentationsx-20260731T150000Z-run"
        assert kwargs["confirmed"] is True
        assert kwargs["storage_root"] == "/tmp/plugin-storage"
        return RunCleanupResult(
            run_key=run_key,
            status="ok",
            message="deleted",
            deleted_sample_count=2,
            deleted_file_count=2,
            custom_run_deleted=True,
            confirmed=True,
        )

    monkeypatch.setattr(delete_run_operator_module, "cleanup_run", fake_cleanup_run)

    assert operator.execute(Context()) == {
        "run_key": "albumentationsx-20260731T150000Z-run",
        "status": "ok",
        "message": "deleted",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "deleted_sample_count": 2,
        "skipped_sample_count": 0,
        "deleted_file_count": 2,
        "skipped_file_count": 0,
        "failed_file_count": 0,
        "custom_run_deleted": True,
        "custom_run_missing": False,
        "confirmed": True,
        "errors_json": "[]",
    }
