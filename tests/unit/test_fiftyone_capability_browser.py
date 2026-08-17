from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.capabilities as capabilities_operator_module
from albumentationsx_plugin.core import CapabilityStatus, TransformCapability
from albumentationsx_plugin.hosts.fiftyone.capabilities import (
    CapabilityBrowserFilters,
    build_capability_browser_result,
    build_capability_filter_choices,
    missing_dependency_browser_result,
)
from albumentationsx_plugin.hosts.fiftyone.operators.capabilities import (
    OPERATOR_NAME,
    ShowAlbumentationsXCapabilities,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeCatalogProvider:
    def __init__(self, capabilities: tuple[TransformCapability, ...]) -> None:
        self._capabilities = capabilities

    @property
    def version_info(self) -> Mapping[str, object]:
        return {
            "albumentationsx": "2.3.8",
            "albu_spec": "0.0.6",
        }

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        return self._capabilities


@pytest.mark.unit
def test_capability_browser_filters_by_name_status_and_target() -> None:
    provider = FakeCatalogProvider(
        (
            TransformCapability(
                name="HorizontalFlip",
                status=CapabilityStatus.SUPPORTED,
                targets=("image", "bboxes", "keypoints"),
                metadata={
                    "parameter_names": ["p"],
                    "transform_type": "dual",
                    "module": "albumentations.augmentations.geometric.flip",
                    "docstring_short": "Flip the input horizontally.",
                },
            ),
            TransformCapability(
                name="Normalize",
                status=CapabilityStatus.UNSUPPORTED_OUTPUT,
                targets=("image",),
                reason_code="non_uint8_image_output",
                message="Transform can produce model-input arrays that are not safe plugin image outputs yet.",
                metadata={
                    "parameter_names": ["mean", "std", "max_pixel_value", "p"],
                    "transform_type": "image_only",
                    "module": "albumentations.augmentations.transforms",
                },
            ),
            TransformCapability(
                name="RandomCrop",
                status=CapabilityStatus.SUPPORTED_WITH_DEFAULTS,
                targets=("image", "mask", "bboxes", "keypoints"),
                reason_code="advanced_parameters_hidden",
                message="Advanced parameters are hidden in the MVP.",
                advanced_parameters=("fill", "fill_mask"),
                metadata={
                    "parameter_names": ["height", "width", "fill", "fill_mask", "p"],
                    "transform_type": "dual",
                    "module": "albumentations.augmentations.crops.transforms",
                },
            ),
        )
    )

    result = build_capability_browser_result(
        CapabilityBrowserFilters(query="crop", status="supported_with_defaults", target="mask"),
        provider=provider,
    )
    payload = result.to_dict()

    assert payload["capability_version_key"] == "albumentationsx-2.3.8__albu-spec-0.0.6"
    assert payload["total_count"] == 3
    assert payload["matching_count"] == 1
    assert payload["supported_count"] == 2
    assert payload["excluded_count"] == 1
    assert payload["matching_status_counts_json"] == '{"supported_with_defaults": 1}'
    assert payload["transforms"] == [
        {
            "name": "RandomCrop",
            "status": "supported_with_defaults",
            "targets": "image, mask, bboxes, keypoints",
            "reason_code": "advanced_parameters_hidden",
            "message": "Advanced parameters are hidden in the MVP.",
            "advanced_parameter_status": "default_only",
            "advanced_parameters": "fill, fill_mask",
            "parameter_count": 5,
            "transform_type": "dual",
            "module": "albumentations.augmentations.crops.transforms",
            "docstring_short": "",
        }
    ]


@pytest.mark.unit
def test_capability_browser_exposes_excluded_reasons() -> None:
    provider = FakeCatalogProvider(
        (
            TransformCapability(
                name="Normalize",
                status=CapabilityStatus.UNSUPPORTED_OUTPUT,
                targets=("image",),
                reason_code="non_uint8_image_output",
                message="Transform can produce model-input arrays that are not safe plugin image outputs yet.",
            ),
        )
    )

    payload = build_capability_browser_result(CapabilityBrowserFilters(), provider=provider).to_dict()
    row = _first_row(payload)

    assert row["status"] == "unsupported_output"
    assert row["reason_code"] == "non_uint8_image_output"
    assert "not safe plugin image outputs" in cast(str, row["message"])


@pytest.mark.unit
def test_capability_filter_choices_are_derived_from_catalog() -> None:
    provider = FakeCatalogProvider(
        (
            TransformCapability(name="HorizontalFlip", status=CapabilityStatus.SUPPORTED, targets=("image", "bboxes")),
            TransformCapability(name="Normalize", status=CapabilityStatus.UNSUPPORTED_OUTPUT, targets=("image",)),
        )
    )

    status_choices, target_choices = build_capability_filter_choices(provider=provider)

    assert status_choices == ("all", "supported", "unsupported_output")
    assert target_choices == ("all", "bboxes", "image")


@pytest.mark.unit
def test_capability_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = ShowAlbumentationsXCapabilities()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Show AlbumentationsX Capabilities"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_capability_operator_resolves_filter_inputs_and_outputs(monkeypatch) -> None:
    operator = ShowAlbumentationsXCapabilities()

    class Context:
        params = {
            "query": "crop",
            "status_filter": "supported_with_defaults",
            "target_filter": "mask",
        }

    monkeypatch.setattr(
        capabilities_operator_module,
        "build_capability_filter_choices",
        lambda: (("all", "supported", "supported_with_defaults"), ("all", "image", "mask")),
    )

    input_json = operator.resolve_input(Context()).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]

    assert input_json["view"]["label"] == "Show AlbumentationsX Capabilities"
    assert input_properties["query"]["default"] == "crop"
    assert input_properties["status_filter"]["type"]["name"] == "Enum"
    assert input_properties["status_filter"]["default"] == "supported_with_defaults"
    assert input_properties["target_filter"]["default"] == "mask"
    assert output_properties["capability_version_key"]["type"]["name"] == "String"
    assert output_properties["total_count"]["type"]["name"] == "Number"
    assert output_properties["transforms"]["type"]["name"] == "List"


@pytest.mark.unit
@pytest.mark.parametrize("missing_name", ("albumentations", "albu_spec"))
def test_capability_operator_resolve_input_missing_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
) -> None:
    error = _missing_module_error(missing_name)

    def raise_missing_dependency() -> None:
        raise error

    monkeypatch.setattr(
        capabilities_operator_module,
        "build_capability_filter_choices",
        raise_missing_dependency,
    )

    input_json = ShowAlbumentationsXCapabilities().resolve_input(ctx=None).to_json()
    properties = input_json["type"]["properties"]
    message_property = properties["missing_runtime_dependency"]

    assert tuple(properties) == ("missing_runtime_dependency",)
    assert message_property["type"]["name"] == "Void"
    assert message_property["view"]["label"] == "Missing runtime dependency"
    assert message_property["view"]["description"] == missing_dependency_browser_result(error)["message"]
    assert "query" not in properties
    assert "status_filter" not in properties
    assert "target_filter" not in properties


@pytest.mark.unit
def test_capability_operator_execute_uses_filters(monkeypatch) -> None:
    operator = ShowAlbumentationsXCapabilities()

    class Context:
        params = {
            "query": "normalize",
            "status_filter": "unsupported_output",
            "target_filter": "image",
        }

    def fake_build_result(filters: CapabilityBrowserFilters) -> Any:
        assert filters == CapabilityBrowserFilters(
            query="normalize",
            status="unsupported_output",
            target="image",
        )

        class Result:
            def to_dict(self) -> dict[str, object]:
                return {"status": "ok", "matching_count": 1}

        return Result()

    monkeypatch.setattr(capabilities_operator_module, "build_capability_browser_result", fake_build_result)

    assert operator.execute(Context()) == {"status": "ok", "matching_count": 1}


@pytest.mark.unit
@pytest.mark.parametrize("missing_name", ("albumentations", "albu_spec"))
def test_capability_operator_execute_missing_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
) -> None:
    error = _missing_module_error(missing_name)

    class Context:
        params = {
            "query": "normalize",
            "status_filter": "unsupported_output",
            "target_filter": "image",
        }

    def raise_missing_dependency(filters: CapabilityBrowserFilters) -> Any:
        assert filters == CapabilityBrowserFilters(query="normalize", status="unsupported_output", target="image")
        raise error

    monkeypatch.setattr(
        capabilities_operator_module,
        "build_capability_browser_result",
        raise_missing_dependency,
    )

    payload = ShowAlbumentationsXCapabilities().execute(Context())

    assert payload == missing_dependency_browser_result(error)
    assert payload["status"] == "error"
    assert payload["albumentationsx_version"] == ""
    assert payload["albu_spec_version"] == ""
    assert payload["capability_version_key"] == ""
    assert payload["total_count"] == 0
    assert payload["matching_count"] == 0
    assert payload["supported_count"] == 0
    assert payload["excluded_count"] == 0
    assert payload["transforms"] == []


@pytest.mark.unit
def test_capability_operator_resolves_samples_grid_placement() -> None:
    operator = ShowAlbumentationsXCapabilities()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "Show AlbumentationsX Capabilities"
    assert view_json["prompt"] is True
    assert "disabled" not in view_json


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


def _first_row(payload: Mapping[str, object]) -> Mapping[str, object]:
    rows = payload["transforms"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, Mapping)
    return row


def _missing_module_error(module_name: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named '{module_name}'", name=module_name)
