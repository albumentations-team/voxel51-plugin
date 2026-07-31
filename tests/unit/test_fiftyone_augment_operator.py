from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.augment as augment_operator_module
from albumentationsx_plugin.hosts.fiftyone.augmentation import FixedAugmentationExecutionResult
from albumentationsx_plugin.hosts.fiftyone.operators.augment import (
    FIXED_SLICE_MESSAGE,
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
    assert config.dynamic is False
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_augment_operator_resolves_fixed_slice_input_and_output() -> None:
    operator = AugmentWithAlbumentationsX()

    input_json = operator.resolve_input(ctx=None).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_json["view"]["label"] == "Augment with AlbumentationsX"
    assert input_properties["transform"]["type"] == {
        "name": "Enum",
        "values": ["HorizontalFlip", "RandomBrightnessContrast", "RandomCrop"],
    }
    assert input_properties["p"]["type"]["name"] == "Number"
    assert input_properties["outputs_per_sample"]["type"]["name"] == "Number"
    assert input_properties["brightness_range_min"]["type"]["name"] == "Number"
    assert input_properties["brightness_range_max"]["type"]["name"] == "Number"
    assert input_properties["contrast_range_min"]["type"]["name"] == "Number"
    assert input_properties["contrast_range_max"]["type"]["name"] == "Number"
    assert input_properties["crop_width"]["type"]["name"] == "Number"
    assert input_properties["crop_height"]["type"]["name"] == "Number"
    assert input_properties["dry_run"]["type"]["name"] == "Boolean"
    assert "status" in input_properties
    assert input_properties["status"]["view"]["description"] == FIXED_SLICE_MESSAGE
    assert output_json["type"]["properties"]["run_key"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["processed_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["created_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["error_count"]["type"]["name"] == "Number"


@pytest.mark.unit
def test_augment_operator_resolves_samples_grid_placement() -> None:
    operator = AugmentWithAlbumentationsX()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "Augment with AlbumentationsX"


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
        )

    monkeypatch.setattr(augment_operator_module, "execute_fixed_augmentation", fake_execute_fixed_augmentation)

    assert operator.execute(Context()) == {
        "run_key": "albumentationsx-20260731T120000Z-test",
        "processed_count": 1,
        "created_count": 1,
        "skipped_count": 0,
        "error_count": 0,
        "dry_run": False,
        "output_tag": "albumentationsx-output",
        "output_dir": "/tmp/outputs",
        "errors": [],
    }
