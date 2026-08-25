from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.view_run as view_run_operator_module
from albumentationsx_plugin.hosts.fiftyone.operators.view_run import (
    OPEN_GENERATED_SAMPLES_FIELD_NAME,
    OPERATOR_NAME,
    OUTPUT_KEY_FIELD_NAME,
    RUN_KEY_FIELD_NAME,
    STORAGE_ROOT_PARAM_NAME,
    ViewAlbumentationsXRun,
)
from albumentationsx_plugin.hosts.fiftyone.run_summary import RunOutputSummary, RunSummary

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

    output = RunOutputSummary(
        key="0|source-1|0|images/output.png",
        position=0,
        label="#1 source=source-1 output_index=0 status=available path=images/output.png",
        status="available",
        source_sample_id="source-1",
        output_index=0,
        output_path="images/output.png",
        generated_sample_id="created-1",
        generated_sample_available=True,
        output_file_available=True,
        replay_available=True,
        replay_record={"replay": {"applied": True}},
    )

    def fake_list_available_run_keys(dataset: object, **kwargs) -> tuple[str, ...]:
        assert dataset is Context.dataset
        assert kwargs["storage_root"] is None
        return ("albumentationsx-20260731T150000Z-first", "albumentationsx-20260731T150000Z-second")

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        assert dataset is Context.dataset
        assert run_key == "albumentationsx-20260731T150000Z-first"
        assert kwargs["selected_output_key"] == ""
        return RunSummary(
            run_key=run_key,
            status="ok",
            message="loaded",
            generated_outputs=(output,),
        )

    monkeypatch.setattr(view_run_operator_module, "list_available_run_keys", fake_list_available_run_keys)
    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

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
    assert input_properties["output_key"]["type"]["name"] == "Enum"
    assert input_properties["output_key"]["default"] == "0|source-1|0|images/output.png"
    assert input_properties["open_generated_samples"]["type"]["name"] == "Boolean"
    assert input_properties["open_generated_samples"]["view"]["name"] == "CheckboxView"
    assert output_properties["status"]["type"]["name"] == "String"
    assert output_properties["cleanup_status"]["type"]["name"] == "String"
    assert output_properties["cleaned_at"]["type"]["name"] == "String"
    assert output_properties["execution_status"]["type"]["name"] == "String"
    assert output_properties["cancelled_at"]["type"]["name"] == "String"
    assert output_properties["run_label"]["type"]["name"] == "String"
    assert output_properties["run_label_slug"]["type"]["name"] == "String"
    assert output_properties["source_count"]["type"]["name"] == "Number"
    assert output_properties["replay_available"]["type"]["name"] == "Boolean"
    assert output_properties["generated_outputs_json"]["type"]["name"] == "String"
    assert output_properties["selected_replay_json"]["type"]["name"] == "String"
    assert output_properties["selected_output_available"]["type"]["name"] == "Boolean"
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
def test_view_run_operator_falls_back_from_stale_param_run_key(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {RUN_KEY_FIELD_NAME: "albumentationsx-20260731T150000Z-deleted"}

    def fake_list_available_run_keys(dataset: object, **kwargs) -> tuple[str, ...]:
        return ("albumentationsx-20260731T150000Z-current",)

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        assert run_key == "albumentationsx-20260731T150000Z-current"
        return RunSummary(run_key=run_key, status="ok", message="loaded")

    monkeypatch.setattr(view_run_operator_module, "list_available_run_keys", fake_list_available_run_keys)
    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    input_json = operator.resolve_input(Context()).to_json()
    run_key_property = input_json["type"]["properties"][RUN_KEY_FIELD_NAME]

    assert run_key_property["type"]["name"] == "Enum"
    assert run_key_property["default"] == "albumentationsx-20260731T150000Z-current"


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
            OUTPUT_KEY_FIELD_NAME: "0|source-1|0|images/output.png",
            STORAGE_ROOT_PARAM_NAME: "/tmp/plugin-storage",
        }

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        assert dataset is Context.dataset
        assert run_key == "albumentationsx-20260731T150000Z-run"
        assert kwargs["storage_root"] == "/tmp/plugin-storage"
        assert kwargs["selected_output_key"] == "0|source-1|0|images/output.png"
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
            generated_outputs=(
                RunOutputSummary(
                    key="0|source-1|0|images/output.png",
                    position=0,
                    label="#1 source=source-1 output_index=0 status=available path=images/output.png",
                    status="available",
                    source_sample_id="source-1",
                    output_index=0,
                    output_path="images/output.png",
                    generated_sample_id="created-1",
                    generated_sample_available=True,
                    output_file_available=True,
                    replay_available=True,
                    replay_record={"replay": {"applied": True}},
                ),
            ),
            selected_output_key="0|source-1|0|images/output.png",
        )

    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    result = operator.execute(Context())

    assert result == {
        "run_key": "albumentationsx-20260731T150000Z-run",
        "status": "ok",
        "message": "loaded",
        "manifest_path": "",
        "fiftyone_run_key": "",
        "cleanup_status": "",
        "cleaned_at": "",
        "execution_status": "",
        "cancelled_at": "",
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
        "generated_sample_ids_json": '["created-1"]',
        "available_generated_sample_ids_json": '["created-1"]',
        "generated_outputs_json": result["generated_outputs_json"],
        "selected_output_key": "0|source-1|0|images/output.png",
        "selected_output_status": "available",
        "selected_source_sample_id": "source-1",
        "selected_generated_sample_id": "created-1",
        "selected_output_index": 0,
        "selected_output_path": "images/output.png",
        "selected_output_available": True,
        "selected_replay_json": '{"replay": {"applied": true}}',
        "plugin_version": "",
        "dependency_versions_json": "{}",
        "pipeline_summary": "HorizontalFlip(p=1.0)",
        "pipeline_config_json": "",
        "errors_json": "",
    }
    assert json.loads(str(result["generated_outputs_json"])) == [
        {
            "key": "0|source-1|0|images/output.png",
            "position": 0,
            "label": "#1 source=source-1 output_index=0 status=available path=images/output.png",
            "status": "available",
            "source_sample_id": "source-1",
            "output_index": 0,
            "output_path": "images/output.png",
            "generated_sample_id": "created-1",
            "generated_sample_available": True,
            "output_file_available": True,
            "replay_available": True,
            "replay_record": {"replay": {"applied": True}},
        }
    ]


@pytest.mark.unit
def test_view_run_operator_can_trigger_generated_sample_view(monkeypatch) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        triggered: list[tuple[str, dict[str, object]]] = []
        params = {
            RUN_KEY_FIELD_NAME: "albumentationsx-20260731T150000Z-run",
            OPEN_GENERATED_SAMPLES_FIELD_NAME: True,
        }

        @classmethod
        def trigger(cls, operator_name: str, params: dict[str, object]) -> None:
            cls.triggered.append((operator_name, params))

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        return RunSummary(
            run_key=run_key,
            status="ok",
            message="loaded",
            generated_outputs=(
                RunOutputSummary(
                    key="0|source-1|0|images/output.png",
                    position=0,
                    label="#1 source=source-1 output_index=0 status=available path=images/output.png",
                    status="available",
                    generated_sample_id="created-1",
                    generated_sample_available=True,
                    output_file_available=True,
                ),
                RunOutputSummary(
                    key="1|source-2|0|images/missing.png",
                    position=1,
                    label="#2 source=source-2 output_index=0 status=missing_sample path=images/missing.png",
                    status="missing_sample",
                    generated_sample_id="missing-created",
                    generated_sample_available=False,
                    output_file_available=True,
                ),
            ),
        )

    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    result = operator.execute(Context())

    assert result["available_generated_sample_ids_json"] == '["created-1"]'
    assert Context.triggered == [("show_samples", {"samples": ["created-1"], "use_extended_selection": False})]


@pytest.mark.unit
def test_view_run_operator_logs_generated_sample_view_trigger_errors(monkeypatch, caplog) -> None:
    operator = ViewAlbumentationsXRun()

    class Ops:
        @staticmethod
        def show_samples(sample_ids: list[str]) -> None:
            raise RuntimeError(f"cannot show {sample_ids}")

    class Context:
        dataset = object()
        ops = Ops()
        params = {
            RUN_KEY_FIELD_NAME: "albumentationsx-20260731T150000Z-run",
            OPEN_GENERATED_SAMPLES_FIELD_NAME: True,
        }

        @classmethod
        def trigger(cls, operator_name: str, params: dict[str, object]) -> None:
            raise RuntimeError(f"{operator_name} failed with {params}")

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        return RunSummary(
            run_key=run_key,
            status="ok",
            message="loaded",
            generated_outputs=(
                RunOutputSummary(
                    key="0|source-1|0|images/output.png",
                    position=0,
                    label="#1 source=source-1 output_index=0 status=available path=images/output.png",
                    status="available",
                    generated_sample_id="created-1",
                    generated_sample_available=True,
                    output_file_available=True,
                ),
            ),
        )

    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)
    caplog.set_level(logging.DEBUG, logger=view_run_operator_module.__name__)

    result = operator.execute(Context())

    assert result["available_generated_sample_ids_json"] == '["created-1"]'
    assert "Error while opening generated samples through ctx.ops.show_samples" in caplog.text
    assert "Error while triggering generated sample view" in caplog.text
