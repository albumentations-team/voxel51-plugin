"""Present inline parameter and image-dimension errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators.types as types

from albumentationsx_plugin.albumentations_backend.image_pipeline import validate_pipeline_image_shape
from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    PluginError,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    AugmentValidationIssue,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    EDITOR_ACTION,
    editor_action,
    execution_params,
)
from albumentationsx_plugin.hosts.fiftyone.forms.defaults import (
    selected_sample_shapes,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_values import _selected_int, _selected_step_count
from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import build_fixed_pipeline_config
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_NAME_FIELD_NAME,
)


def _mark_validation_fields(inputs: types.Object, issues: tuple[AugmentValidationIssue, ...]) -> None:
    for issue in issues:
        names = issue.fields
        if not names:
            names = (SAVE_PRESET_NAME_FIELD_NAME,) if issue.context.get("preset_name_field") else (EDITOR_ACTION,)
        for name in names:
            _mark_field(inputs, name, issue.message)


def _dimension_issues(ctx: Any, params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    config = build_fixed_pipeline_config(execution_params(params))
    stages = sorted(
        (
            _selected_int(
                params.get(pipeline_stage_order_field_name(number)),
                default=number,
                min_value=1,
                max_value=MAX_PIPELINE_STEPS,
            ),
            number,
        )
        for number in range(1, _selected_step_count(params.get(PIPELINE_STEP_COUNT_FIELD_NAME)) + 1)
        if params.get(pipeline_stage_enabled_field_name(number)) is not False
    )
    shapes = selected_sample_shapes(ctx)
    if editor_action(params) == "preview":
        shapes = shapes[:3]
    for sample_id, shape in shapes:
        try:
            validate_pipeline_image_shape(config, image_shape=shape)
        except PluginError as error:
            position = error.context.get("execution_stage")
            number = stages[int(position) - 1][1] if isinstance(position, int) else 1
            parameter = str(error.context.get("parameter_name", "transform"))
            return (
                AugmentValidationIssue(
                    error.code.value,
                    f"Sample {sample_id}, stage {number}: {error.message}",
                    {**error.context, "sample_id": sample_id, "stage_number": number},
                    (pipeline_step_field_name(number, parameter),),
                ),
            )
    return ()


def _mark_field(inputs: types.Object, name: str, message: str) -> bool:
    for key, prop in inputs.properties.items():
        if key == name:
            prop.invalid = True
            prop.error_message = message
            return True
        if isinstance(prop.type, types.Object) and _mark_field(prop.type, name, message):
            if prop.view is not None and hasattr(prop.view, "componentsProps"):
                grid = (prop.view.componentsProps or {}).get("grid", {})
                if grid.get("component") == "details":
                    grid["open"] = True
            return True
    return False


def _focus_first_invalid(inputs: types.Object) -> bool:
    for prop in inputs.properties.values():
        if isinstance(prop.type, types.Object):
            if _focus_first_invalid(prop.type):
                return True
        elif prop.invalid and isinstance(prop.view, types.FieldView):
            props = dict(getattr(prop.view, "componentsProps", {}) or {})
            # TextFieldView consumes `field`, not `input`. Changing the wrapper
            # element remounts the input when it first becomes invalid, so
            # autofocus also works after an edit, not only on initial render.
            props["field"] = {**props.get("field", {}), "autoFocus": True}
            props["container"] = {**props.get("container", {}), "component": "section"}
            # View.to_json merges constructor kwargs last; reconstruct instead
            # of assigning an attribute that those kwargs would overwrite.
            prop.view = types.FieldView(**{**prop.view.to_json(), "componentsProps": props})
            return True
    return False
