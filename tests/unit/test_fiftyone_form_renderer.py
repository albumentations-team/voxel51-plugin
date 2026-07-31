from __future__ import annotations

import importlib
import sys

import pytest

from albumentationsx_plugin.core import FieldKind, FormFieldSchema, HostAdapterError
from albumentationsx_plugin.hosts.fiftyone.forms import (
    UnsupportedFormFieldError,
    render_form,
)


@pytest.mark.unit
def test_fiftyone_form_renderer_maps_supported_field_kinds() -> None:
    form_json = render_form(
        (
            FormFieldSchema(
                name="enabled",
                kind=FieldKind.BOOLEAN,
                label="Enabled",
                default=True,
                help_text="Whether this option is enabled.",
            ),
            FormFieldSchema(
                name="count",
                kind=FieldKind.INTEGER,
                label="Count",
                required=True,
                default=2,
                min_value=1,
                max_value=5,
            ),
            FormFieldSchema(
                name="probability",
                kind=FieldKind.FLOAT,
                label="Probability",
                default=0.5,
                min_value=0.0,
                max_value=1.0,
            ),
            FormFieldSchema(name="note", kind=FieldKind.STRING, label="Note"),
            FormFieldSchema(
                name="mode",
                kind=FieldKind.ENUM,
                label="Mode",
                required=True,
                default="fast",
                choices=("fast", "accurate"),
            ),
            FormFieldSchema(
                name="optional_mode",
                kind=FieldKind.ENUM,
                label="Optional mode",
                choices=("auto", None),
            ),
            FormFieldSchema(
                name="crop_size",
                kind=FieldKind.NUMBER_RANGE,
                label="Crop size",
                default=[32, 64],
                item_schema={"kind": "integer"},
            ),
            FormFieldSchema(
                name="channel_order",
                kind=FieldKind.LIST,
                label="Channel order",
                default=[2, 1, 0],
                item_schema={"kind": "integer", "length": 3},
            ),
            FormFieldSchema(
                name="fill",
                kind=FieldKind.JSON,
                label="Fill",
                default=0.0,
            ),
        ),
    ).to_json()

    properties = form_json["properties"]

    assert properties["enabled"]["type"]["name"] == "Boolean"
    assert properties["enabled"]["default"] is True
    assert properties["enabled"]["view"]["description"] == "Whether this option is enabled."
    assert properties["count"]["type"] == {
        "name": "Number",
        "int": True,
        "float": False,
        "min": 1.0,
        "max": 5.0,
    }
    assert properties["count"]["required"] is True
    assert properties["probability"]["type"] == {
        "name": "Number",
        "int": False,
        "float": True,
        "min": 0.0,
        "max": 1.0,
    }
    assert properties["note"]["type"] == {"name": "String", "allow_empty": True}
    assert properties["mode"]["type"] == {"name": "Enum", "values": ["fast", "accurate"]}
    assert properties["optional_mode"]["type"] == {"name": "Enum", "values": ["auto", None]}
    assert properties["crop_size"]["type"]["name"] == "Tuple"
    assert properties["crop_size"]["type"]["items"] == [
        {"name": "Number", "min": None, "max": None, "int": True, "float": False},
        {"name": "Number", "min": None, "max": None, "int": True, "float": False},
    ]
    assert properties["channel_order"]["type"] == {
        "name": "List",
        "element_type": {"name": "Number", "min": None, "max": None, "int": True, "float": False},
        "min_items": 3,
        "max_items": 3,
    }
    assert properties["fill"]["type"] == {"name": "String", "allow_empty": True}
    assert properties["fill"]["default"] == "0.0"


@pytest.mark.unit
def test_fiftyone_form_renderer_raises_for_unsupported_field_kind() -> None:
    field = FormFieldSchema(
        name="advanced",
        kind=FieldKind.OBJECT,
        properties=(FormFieldSchema(name="nested", kind=FieldKind.STRING),),
    )

    with pytest.raises(UnsupportedFormFieldError) as error:
        render_form((field,))

    assert error.value.reason_code == "host_adapter_error"
    assert error.value.context == {
        "host": "fiftyone",
        "field_name": "advanced",
        "field_kind": "object",
    }


@pytest.mark.unit
def test_fiftyone_form_renderer_rejects_enum_choices_that_fiftyone_cannot_render() -> None:
    field = FormFieldSchema(
        name="mode",
        kind=FieldKind.ENUM,
        choices=({"label": "fast"},),
    )

    with pytest.raises(HostAdapterError) as error:
        render_form((field,))

    assert error.value.context["field_name"] == "mode"
    assert error.value.context["field_kind"] == "enum"


@pytest.mark.unit
def test_fiftyone_form_renderer_does_not_import_albumentations_runtime() -> None:
    for module_name in ("albumentations", "albu_spec"):
        sys.modules.pop(module_name, None)

    importlib.import_module("albumentationsx_plugin.hosts.fiftyone.forms")

    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules
