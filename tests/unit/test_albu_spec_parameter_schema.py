from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from typing import Any

import pytest

from albumentationsx_plugin.albumentations_backend.parameters import (
    AlbuSpecParameterSchemaProvider,
    build_albu_spec_parameter_schema_snapshot,
    build_parameter_field_schema,
    is_parameter_required,
)
from albumentationsx_plugin.albumentations_backend.parameters.conversion import (
    SCHEMA_STATUS_JSON_FALLBACK,
    SCHEMA_STATUS_SUPPORTED,
    SCHEMA_STATUS_UNSUPPORTED_REQUIRED,
)
from albumentationsx_plugin.core import FieldKind, UnsupportedTransformError


@dataclass(frozen=True, slots=True)
class FakeParameter:
    name: str
    type_hint: Any
    default: object = None
    description: str | None = None
    constraints: object | None = None


@dataclass(frozen=True, slots=True)
class FakeConstraints:
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None


@pytest.mark.unit
def test_albu_spec_parameter_provider_generates_fixed_transform_fields() -> None:
    provider = AlbuSpecParameterSchemaProvider()

    horizontal_flip = provider.get_parameter_schema("HorizontalFlip")
    random_brightness_contrast = provider.get_parameter_schema("RandomBrightnessContrast")
    random_crop = provider.get_parameter_schema("RandomCrop")

    assert [(field.name, field.kind, field.default) for field in horizontal_flip] == [
        ("p", FieldKind.FLOAT, 0.5),
    ]
    assert horizontal_flip[0].min_value == 0
    assert horizontal_flip[0].max_value == 1
    assert horizontal_flip[0].required is False

    brightness_range = _field_by_name(random_brightness_contrast, "brightness_range")
    assert brightness_range.kind == FieldKind.NUMBER_RANGE
    assert brightness_range.default == [-0.2, 0.2]
    assert brightness_range.item_schema == {"kind": "float"}
    assert brightness_range.metadata["schema_status"] == SCHEMA_STATUS_SUPPORTED

    height = _field_by_name(random_crop, "height")
    assert height.kind == FieldKind.INTEGER
    assert height.required is True
    assert height.min_value == 1

    pad_position = _field_by_name(random_crop, "pad_position")
    assert pad_position.kind == FieldKind.ENUM
    assert pad_position.choices == ("center", "top_left", "top_right", "bottom_left", "bottom_right", "random")

    fill = _field_by_name(random_crop, "fill")
    assert fill.kind == FieldKind.JSON
    assert fill.metadata["schema_status"] == SCHEMA_STATUS_JSON_FALLBACK
    assert fill.metadata["reason_code"] == "complex_optional_parameter"


@pytest.mark.unit
def test_albu_spec_parameter_provider_supports_enums_optional_values_and_lists() -> None:
    provider = AlbuSpecParameterSchemaProvider()

    to_gray = provider.get_parameter_schema("ToGray")
    d4 = provider.get_parameter_schema("D4")
    channel_swap = provider.get_parameter_schema("ChannelSwap")

    method = _field_by_name(to_gray, "method")
    assert method.kind == FieldKind.ENUM
    assert "weighted_average" in method.choices
    assert "pca" in method.choices

    group_element = _field_by_name(d4, "group_element")
    assert group_element.kind == FieldKind.ENUM
    assert group_element.required is False
    assert None in group_element.choices

    channel_order = _field_by_name(channel_swap, "channel_order")
    assert channel_order.kind == FieldKind.LIST
    assert channel_order.default == [2, 1, 0]
    assert channel_order.item_schema == {"kind": "integer"}


@pytest.mark.unit
def test_albu_spec_parameter_schema_is_json_serializable_and_deterministic() -> None:
    snapshot = build_albu_spec_parameter_schema_snapshot(
        ("HorizontalFlip", "RandomBrightnessContrast", "RandomCrop", "ToGray", "D4"),
    )

    decoded = json.loads(json.dumps(snapshot))

    assert decoded["version_key"] == "albumentationsx-2.3.7__albu-spec-0.0.6"
    assert decoded["transform_names"] == [
        "HorizontalFlip",
        "RandomBrightnessContrast",
        "RandomCrop",
        "ToGray",
        "D4",
    ]
    assert decoded["schemas"]["HorizontalFlip"][0]["name"] == "p"
    assert decoded["schemas"]["RandomCrop"][0]["name"] == "height"


@pytest.mark.unit
def test_unsupported_required_parameters_are_marked_with_reason_codes() -> None:
    parameter = FakeParameter(
        name="callback",
        type_hint="Callable[..., Any]",
        default=None,
        description="Runtime callback.",
    )

    field = build_parameter_field_schema(parameter)

    assert is_parameter_required(parameter) is True
    assert field.kind == FieldKind.JSON
    assert field.required is True
    assert field.metadata["schema_status"] == SCHEMA_STATUS_UNSUPPORTED_REQUIRED
    assert field.metadata["reason_code"] == "unsupported_required_parameter"


@pytest.mark.unit
def test_simple_list_type_hints_are_supported() -> None:
    parameter = FakeParameter(
        name="indices",
        type_hint="list[int] | None",
        default=None,
    )

    field = build_parameter_field_schema(parameter)

    assert field.kind == FieldKind.LIST
    assert field.required is False
    assert field.item_schema == {"kind": "integer"}


@pytest.mark.unit
def test_constraints_are_preserved_on_generated_fields() -> None:
    parameter = FakeParameter(
        name="alpha",
        type_hint="float",
        default=0.5,
        constraints=FakeConstraints(ge=0.0, le=1.0),
    )

    field = build_parameter_field_schema(parameter)

    assert field.kind == FieldKind.FLOAT
    assert field.min_value == 0
    assert field.max_value == 1
    assert field.metadata["constraints"] == {"ge": 0.0, "le": 1.0}


@pytest.mark.unit
def test_parameter_schema_provider_rejects_unknown_or_excluded_transforms() -> None:
    provider = AlbuSpecParameterSchemaProvider()

    with pytest.raises(UnsupportedTransformError, match="not known"):
        provider.get_parameter_schema("MissingTransform")

    with pytest.raises(UnsupportedTransformError, match="not available"):
        provider.get_parameter_schema("Normalize")


@pytest.mark.unit
def test_parameter_schema_package_does_not_import_fiftyone() -> None:
    sys.modules.pop("fiftyone", None)
    importlib.import_module("albumentationsx_plugin.albumentations_backend.parameters")

    assert "fiftyone" not in sys.modules


def _field_by_name(fields: tuple[Any, ...], name: str) -> Any:
    for field in fields:
        if field.name == name:
            return field
    raise AssertionError(f"Field {name} was not generated")
