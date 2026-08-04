from __future__ import annotations

import importlib
import pathlib
import sys
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.augment as augment_operator_module
from albumentationsx_plugin.hosts.fiftyone.augmentation import FixedAugmentationExecutionResult
from albumentationsx_plugin.hosts.fiftyone.operators.augment import (
    OPERATOR_NAME,
    AugmentWithAlbumentationsX,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


@pytest.mark.unit
def test_augment_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = AugmentWithAlbumentationsX()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Augment with AlbumentationsX"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_augment_operator_module_import_does_not_load_backend_dependencies() -> None:
    for module_name in ("albumentations", "albu_spec"):
        sys.modules.pop(module_name, None)

    importlib.reload(augment_operator_module)

    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_augment_operator_resolves_dynamic_default_input_and_output() -> None:
    operator = AugmentWithAlbumentationsX()

    input_json = operator.resolve_input(ctx=None).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_json["view"]["label"] == "Augment with AlbumentationsX"
    assert input_properties["pipeline_step_count"]["type"]["name"] == "Number"
    assert input_properties["pipeline_step_count"]["default"] == 1
    assert input_properties["pipeline_step_count"]["required"] is False
    transform_values = input_properties["transform"]["type"]["values"]
    assert input_properties["transform"]["type"]["name"] == "Enum"
    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["transform"]["required"] is False
    assert input_properties["transform"]["view"]["name"] == "AutocompleteView"
    assert "HorizontalFlip" in transform_values
    assert "RandomBrightnessContrast" in transform_values
    assert "RandomCrop" in transform_values
    assert "ToGray" not in transform_values
    assert "Normalize" not in transform_values
    assert input_properties["p"]["type"]["name"] == "Number"
    assert input_properties["p"]["default"] == 1.0
    assert input_properties["outputs_per_sample"]["type"]["name"] == "Number"
    assert input_properties["outputs_per_sample"]["required"] is False
    assert input_properties["outputs_per_sample"]["default"] == 1
    assert input_properties["dry_run"]["type"]["name"] == "Boolean"
    assert output_json["type"]["properties"]["run_key"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["processed_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["created_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["error_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["manifest_path"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["fiftyone_run_key"]["type"]["name"] == "String"


@pytest.mark.unit
def test_augment_operator_resolves_ordered_pipeline_steps() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {
            "pipeline_step_count": 2,
            "transform": "HorizontalFlip",
            "step_2_transform": "RandomBrightnessContrast",
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["pipeline_step_count"]["default"] == 2
    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["step_2_transform"]["default"] == "RandomBrightnessContrast"
    assert input_properties["step_2_brightness_range"]["type"]["name"] == "Tuple"
    assert input_properties["step_2_contrast_range"]["type"]["name"] == "Tuple"
    assert input_properties["step_2_p"]["default"] == 1.0
    assert "step_2_brightness_by_max" not in input_properties
    assert "step_2_ensure_safe_output" not in input_properties
    assert "step_3_transform" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolves_later_step_random_crop_defaults() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {
            "pipeline_step_count": 3,
            "transform": "HorizontalFlip",
            "step_2_transform": "RandomBrightnessContrast",
            "step_3_transform": "RandomCrop",
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["step_3_height"]["required"] is False
    assert input_properties["step_3_height"]["default"] == 32
    assert input_properties["step_3_width"]["required"] is False
    assert input_properties["step_3_width"]["default"] == 32
    assert input_properties["step_3_p"]["default"] == 1.0
    assert "step_3_pad_if_needed" not in input_properties
    assert "step_3_border_mode" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolve_input_reports_missing_runtime_dependency(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    def fake_build_dynamic_augment_form(_ctx: object):
        raise ModuleNotFoundError("No module named 'albu_spec'", name="albu_spec")

    monkeypatch.setattr(augment_operator_module, "_build_dynamic_augment_form", fake_build_dynamic_augment_form)

    input_json = operator.resolve_input(ctx=None).to_json()
    message = input_json["type"]["properties"]["missing_runtime_dependency"]

    assert message["view"]["label"] == "Missing runtime dependency"
    assert "albu-spec" in message["view"]["description"]


@pytest.mark.unit
def test_augment_operator_resolves_selected_transform_parameter_schema() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "RandomBrightnessContrast"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["brightness_range"]["type"]["name"] == "Tuple"
    assert input_properties["brightness_range"]["default"] == [-0.2, 0.2]
    assert input_properties["contrast_range"]["type"]["name"] == "Tuple"
    assert input_properties["contrast_range"]["default"] == [-0.2, 0.2]
    assert input_properties["p"]["default"] == 1.0
    assert "brightness_by_max" not in input_properties
    assert "ensure_safe_output" not in input_properties
    assert "execution_scope" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolves_random_crop_without_initial_required_errors() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["required"] is False
    assert input_properties["height"]["default"] == 32
    assert input_properties["width"]["required"] is False
    assert input_properties["width"]["default"] == 32
    assert input_properties["p"]["default"] == 1.0
    assert "pad_if_needed" not in input_properties
    assert "pad_position" not in input_properties
    assert "border_mode" not in input_properties


@pytest.mark.unit
def test_augment_operator_ignores_non_executable_catalog_transform_selection() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "ToGray"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["p"]["type"]["name"] == "Number"
    assert "method" not in input_properties
    assert "execution_scope" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolves_samples_grid_placement() -> None:
    operator = AugmentWithAlbumentationsX()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "Augment with AlbumentationsX"
    assert view_json["prompt"] is True


@pytest.mark.unit
def test_augment_operator_execute_delegates_to_fixed_executor(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        view = object()
        selected = ("sample-1",)
        params = {"transform": "HorizontalFlip"}

    def fake_execute_fixed_augmentation(**kwargs):
        assert kwargs["dataset"] is Context.dataset
        assert kwargs["view"] is Context.view
        assert kwargs["selected_sample_ids"] == ("sample-1",)
        assert kwargs["params"] == {"transform": "HorizontalFlip"}
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-test",
            processed_count=1,
            created_count=1,
            skipped_count=0,
            error_count=0,
            dry_run=False,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
            manifest_path="/tmp/outputs/manifest.json",
            fiftyone_run_key="albumentationsx_20260731T120000Z_test",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    assert operator.execute(Context()) == {
        "run_key": "albumentationsx-20260731T120000Z-test",
        "processed_count": 1,
        "created_count": 1,
        "skipped_count": 0,
        "error_count": 0,
        "dry_run": False,
        "output_tag": "albumentationsx-output",
        "output_dir": "/tmp/outputs",
        "manifest_path": "/tmp/outputs/manifest.json",
        "fiftyone_run_key": "albumentationsx_20260731T120000Z_test",
        "errors": [],
    }


@pytest.mark.unit
def test_augment_operator_execute_reports_missing_runtime_dependency(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        selected = ()
        params: dict[str, object] = {}

    def fake_execute_fixed_augmentation(**_kwargs: object):
        raise ModuleNotFoundError("No module named 'albumentations'", name="albumentations")

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["error_count"] == 1
    errors = result["errors"]
    assert isinstance(errors, list)
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"] == "missing_runtime_dependency"
    assert first_error["context"] == {
        "missing_module": "albumentations",
        "package": "albumentationsx",
    }
