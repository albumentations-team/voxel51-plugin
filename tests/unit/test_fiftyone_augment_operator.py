from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

from albumentationsx_plugin.hosts.fiftyone.operators.augment import (
    OPERATOR_NAME,
    PLACEHOLDER_MESSAGE,
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
def test_augment_operator_resolves_placeholder_input_and_output() -> None:
    operator = AugmentWithAlbumentationsX()

    input_json = operator.resolve_input(ctx=None).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_json["view"]["label"] == "Augment with AlbumentationsX"
    assert input_properties["transform"]["type"] == {"name": "Enum", "values": ["HorizontalFlip"]}
    assert input_properties["outputs_per_sample"]["type"]["name"] == "Number"
    assert input_properties["dry_run"]["type"]["name"] == "Boolean"
    assert "status" in input_properties
    assert output_json["type"]["properties"]["ready"]["type"]["name"] == "Boolean"
    assert output_json["type"]["properties"]["message"]["type"]["name"] == "String"


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
def test_augment_operator_execute_is_noop_placeholder() -> None:
    operator = AugmentWithAlbumentationsX()

    assert operator.execute(ctx=None) == {
        "ready": False,
        "message": PLACEHOLDER_MESSAGE,
    }
