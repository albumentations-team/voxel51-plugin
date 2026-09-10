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
from albumentationsx_plugin.hosts.fiftyone.run_library import RunLibraryEntry
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
    assert config.label == "AlbumentationsX · Run history"
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

    monkeypatch.setattr(
        view_run_operator_module,
        "list_run_library",
        lambda dataset, **kwargs: tuple(
            RunLibraryEntry(run_key=key) for key in fake_list_available_run_keys(dataset, **kwargs)
        ),
    )
    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    input_json = operator.resolve_input(Context()).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]

    assert input_json["view"]["label"] == "AlbumentationsX · Run history"
    assert input_properties["run_key"]["type"]["name"] == "Enum"
    assert input_properties["run_key"]["type"]["values"] == (
        "albumentationsx-20260731T150000Z-first",
        "albumentationsx-20260731T150000Z-second",
    )
    assert input_properties["run_key"]["default"] == "albumentationsx-20260731T150000Z-first"
    assert input_properties["run_key"]["view"]["name"] == "AutocompleteView"
    assert input_properties["_output_inspection"]["type"]["properties"]["output_key"]["type"]["name"] == "Enum"
    assert (
        input_properties["_output_inspection"]["type"]["properties"]["output_key"]["default"]
        == "0|source-1|0|images/output.png"
    )
    assert (
        input_properties["_output_inspection"]["type"]["properties"]["open_generated_samples"]["type"]["name"]
        == "Boolean"
    )
    assert (
        input_properties["_output_inspection"]["type"]["properties"]["open_generated_samples"]["view"]["name"]
        == "CheckboxView"
    )
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

    monkeypatch.setattr(view_run_operator_module, "list_run_library", lambda dataset, **kwargs: ())

    input_json = operator.resolve_input(Context()).to_json()
    run_key_property = input_json["type"]["properties"]["run_key"]

    assert run_key_property["type"]["name"] == "String"
    assert "No persisted AlbumentationsX runs" in run_key_property["view"]["description"]


@pytest.mark.unit
@pytest.mark.parametrize("stale_key", ["albumentationsx-20260731T150000Z-deleted", None, ""])
def test_view_run_operator_requires_selection_after_filter_excludes_current_run(monkeypatch, stale_key) -> None:
    operator = ViewAlbumentationsXRun()

    class Context:
        dataset = object()
        params = {RUN_KEY_FIELD_NAME: stale_key}

    def fake_list_available_run_keys(dataset: object, **kwargs) -> tuple[str, ...]:
        return ("albumentationsx-20260731T150000Z-current",)

    def fake_build_run_summary(dataset: object, run_key: str, **kwargs) -> RunSummary:
        assert run_key == "albumentationsx-20260731T150000Z-current"
        return RunSummary(run_key=run_key, status="ok", message="loaded")

    monkeypatch.setattr(
        view_run_operator_module,
        "list_run_library",
        lambda dataset, **kwargs: tuple(
            RunLibraryEntry(run_key=key) for key in fake_list_available_run_keys(dataset, **kwargs)
        ),
    )
    monkeypatch.setattr(view_run_operator_module, "build_run_summary", fake_build_run_summary)

    input_json = operator.resolve_input(Context()).to_json()
    run_key_property = input_json["type"]["properties"][RUN_KEY_FIELD_NAME]

    assert run_key_property["type"]["name"] == "Enum"
    assert run_key_property["default"] == ""
    assert run_key_property["invalid"] is True
    props = input_json["type"]["properties"]
    assert "delete_run_outputs" not in props and "_load_pipeline" not in props
    assert run_key_property["view"]["componentsProps"]["autocomplete"]["value"] is None


@pytest.mark.unit
def test_view_run_operator_leaves_toolbar_placement_to_frontend() -> None:
    assert ViewAlbumentationsXRun().resolve_placement(ctx=None) is None


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

    assert {key: value for key, value in result.items() if key != "_result_details"} == {
        "created_at": "",
        "execution_scope": "",
        "library_status": "ok",
        "manifest_json": "",
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
        "skipped_count": 0,
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


@pytest.mark.unit
@pytest.mark.parametrize("status", ["completed", "failed", "partial", "cancelled", "cleaned", "missing_manifest"])
def test_run_library_exposes_named_runs_and_safe_actions(monkeypatch, status):
    from types import SimpleNamespace

    entry = RunLibraryEntry(
        run_key="cats-run",
        run_label="Cats",
        status=status,
        created_at="2026-09-09T12:00:00+00:00",
        source_count=5,
        output_count=3,
        error_count=2,
        execution_scope="current_view",
        manifest_available=status != "missing_manifest",
    )
    monkeypatch.setattr(view_run_operator_module, "list_run_library", lambda *args, **kwargs: (entry,))
    monkeypatch.setattr(
        view_run_operator_module,
        "build_run_summary",
        lambda *args, **kwargs: RunSummary(run_key=entry.run_key, status="ok", message="loaded"),
    )
    ctx = SimpleNamespace(dataset=object(), params={"_storage_root": "/tmp/library"})
    properties = ViewAlbumentationsXRun().resolve_input(ctx).to_json()["type"]["properties"]
    choice = properties["run_key"]["view"]["choices"][0]
    assert choice["label"].startswith("Cats |")
    assert status in choice["label"]
    assert "Sources: 5" in properties["run_details"]["view"]["description"]
    assert "Cats" in properties["run_details"]["view"]["label"]
    assert "reuse_pipeline" not in properties  # Only the editable snapshot loader is used.
    if status in {"cleaned", "missing_manifest"}:
        assert "delete_run_outputs" not in properties
    else:
        delete = properties["delete_run_outputs"]["view"]
        assert delete["prompt"] is True
        assert delete["params"] == {
            "run_key": "cats-run",
            "confirm_delete": False,
            "_storage_root": "/tmp/library",
            "_history_run": True,
        }


@pytest.mark.unit
def test_run_library_search_and_hide_cleaned(monkeypatch):
    from types import SimpleNamespace

    entries = (
        RunLibraryEntry(run_key="cleaned", run_label="Cats", status="cleaned"),
        RunLibraryEntry(run_key="active", run_label="Dogs", status="completed", pipeline_summary="HorizontalFlip"),
    )
    monkeypatch.setattr(view_run_operator_module, "list_run_library", lambda *args, **kwargs: entries)
    monkeypatch.setattr(
        view_run_operator_module,
        "build_run_summary",
        lambda dataset, key, **kwargs: RunSummary(run_key=key, status="ok", message="loaded"),
    )
    ctx = SimpleNamespace(dataset=object(), params={"show_cleaned": False, "run_query": "FLIP"})
    props = ViewAlbumentationsXRun().resolve_input(ctx).to_json()["type"]["properties"]
    assert props["run_key"]["type"]["values"] == ("active",)
    ctx.params["run_query"] = "Cats"
    props = ViewAlbumentationsXRun().resolve_input(ctx).to_json()["type"]["properties"]
    assert "run_details" not in props
    assert "_load_pipeline" not in props
