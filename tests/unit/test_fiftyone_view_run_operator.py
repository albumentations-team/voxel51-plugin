from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.view_run as view_run_operator_module
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    OPERATOR_NAME,
    STORAGE_ROOT_PARAM_NAME,
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.run_summary import RunSummary

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


@pytest.mark.unit
def test_view_run_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = ViewAlbumentationsXRun()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "View AlbumentationsX Run"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_view_run_operator_resolves_run_selector_and_output(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {}

    def fake_list_available_run_keys(dataset: object, **kwargs) -> tuple[str, ...]:
        assert dataset is Context.dataset
        assert kwargs["storage_root"] is None
        return ("albumentationsx-20260731T150000Z-first", "albumentationsx-20260731T150000Z-second")

    monkeypatch.setattr(view_run_operator_module, "list_available_run_keys", fake_list_available_run_keys)

    input_json = operator.resolve_input(Context()).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]

    assert input_json["view"]["label"] == "View AlbumentationsX Run"
    assert input_properties["run_key"]["type"]["name"] == "Enum"
    assert input_properties["run_key"]["type"]["values"] == (
        "albumentationsx-20260731T150000Z-first",
        "albumentationsx-20260731T150000Z-second",
    )
    assert input_properties["run_key"]["default"] == "albumentationsx-20260731T150000Z-first"
    assert input_properties["run_key"]["view"]["name"] == "AutocompleteView"
    assert output_properties["status"]["type"]["name"] == "String"
    assert output_properties["cleanup_status"]["type"]["name"] == "String"
    assert output_properties["cleaned_at"]["type"]["name"] == "String"
    assert output_properties["run_label"]["type"]["name"] == "String"
    assert output_properties["run_label_slug"]["type"]["name"] == "String"
    assert output_properties["source_count"]["type"]["name"] == "Number"
    assert output_properties["replay_available"]["type"]["name"] == "Boolean"
    assert output_properties["pipeline_config_json"]["type"]["name"] == "String"


@pytest.mark.unit
def test_view_run_operator_resolves_empty_selector_without_dataset_runs(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {}

    monkeypatch.setattr(view_run_operator_module, "list_available_run_keys", lambda dataset, **kwargs: ())

    input_json = operator.resolve_input(Context()).to_json()
    run_key_property = input_json["type"]["properties"]["run_key"]

    assert run_key_property["type"]["name"] == "String"
    assert "No persisted AlbumentationsX runs" in run_key_property["view"]["description"]


@pytest.mark.unit
def test_view_run_operator_resolves_samples_grid_placement() -> None:
    operator = ViewAlbumentationsXRun()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "View AlbumentationsX Run"
    assert view_json["prompt"] is True
    assert view_json["disabled"] is True


@pytest.mark.unit
def test_view_run_operator_enables_samples_grid_placement_with_dataset_runs(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {}

    monkeypatch.setattr(
        view_run_operator_module,
        "list_available_run_keys",
        lambda dataset, **kwargs: ("albumentationsx-20260731T150000Z-run",),
    )

    placement_json = operator.resolve_placement(Context()).to_json()
    view_json = placement_json["view"]

    assert isinstance(view_json, dict)
    assert view_json["disabled"] is False
    assert view_json["title"] is None


@pytest.mark.unit
def test_view_run_operator_execute_delegates_to_summary_service(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {
            "run_key": "albumentationsx-20260731T150000Z-run",
            STORAGE_ROOT_PARAM_NAME: "/tmp/plugin-storage",
        }

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        assert dataset is Context.dataset
        assert run_key == "albumentationsx-20260731T150000Z-run"
        assert kwargs["storage_root"] == "/tmp/plugin-storage"
        return RunSummary(
            run_key=run_key,
            status="ok",
            message="loaded",
            cleanup_status="",
            cleaned_at="",
            run_label="Cats crop test",
            run_label_slug="cats-crop-test",
            source_count=2,
            created_count=2,
            pipeline_summary="HorizontalFlip(p=1.0)",
        )

    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    assert operator.execute(Context()) == {
        "run_key": "albumentationsx-20260731T150000Z-run",
        "status": "ok",
        "message": "loaded",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "cleanup_status": "",
        "cleaned_at": "",
        "run_label": "Cats crop test",
        "run_label_slug": "cats-crop-test",
        "source_count": 2,
        "created_count": 2,
        "output_count": 0,
        "available_output_count": 0,
        "missing_output_count": 0,
        "error_count": 0,
        "replay_count": 0,
        "replay_available": False,
        "output_tag": "",
        "output_dir": "",
        "plugin_version": "",
        "dependency_versions_json": "{}",
        "pipeline_summary": "HorizontalFlip(p=1.0)",
        "pipeline_config_json": "",
        "errors_json": "",
    }
