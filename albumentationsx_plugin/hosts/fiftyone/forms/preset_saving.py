"""Explicit create/update controls for the augmentation editor."""

from __future__ import annotations

from collections.abc import Mapping

import fiftyone.operators.types as types

from albumentationsx_plugin.hosts.fiftyone.editor_draft import editor_action
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_CONFIRM_FIELD_NAME,
    SAVE_PRESET_MODE_FIELD_NAME,
    SAVE_PRESET_TARGET_FIELD_NAME,
    preset_update_target,
)
from albumentationsx_plugin.hosts.fiftyone.preset_management import storage_root_from_params
from albumentationsx_plugin.storage import FilePipelinePresetStore


def render_preset_save_controls(inputs: types.Object, params: Mapping[str, object]) -> None:
    """Keep the update target independent of the pipeline load picker."""
    mode = params.get(SAVE_PRESET_MODE_FIELD_NAME, "new")
    choices = types.RadioGroup()
    choices.add_choice("new", label="Save as new pipeline")
    choices.add_choice("update", label="Update existing pipeline")
    inputs.enum(
        SAVE_PRESET_MODE_FIELD_NAME,
        ["new", "update"],
        default=mode,
        label="Save mode",
        view=choices,
        description="Save as new creates a separate pipeline even when the display name already exists.",
    )
    if mode != "update":
        return
    store = FilePipelinePresetStore(storage_root=storage_root_from_params(params))
    choices = types.AutocompleteView(allow_user_input=False)
    try:
        presets = store.list_presets()
    except Exception:
        presets = ()
    for preset in presets:
        choices.add_choice(preset.key, label=f"{preset.name} ({preset.key})")
    target = inputs.enum(
        SAVE_PRESET_TARGET_FIELD_NAME,
        [preset.key for preset in presets],
        label="Pipeline to replace",
        default=params.get(SAVE_PRESET_TARGET_FIELD_NAME, ""),
        required=editor_action(params) == "save",
        view=choices,
        description="Select the exact saved pipeline to update. Load pipeline does not choose this target.",
    )
    selected = next((preset for preset in presets if preset.key == params.get(SAVE_PRESET_TARGET_FIELD_NAME)), None)
    confirmations = params.get(SAVE_PRESET_CONFIRM_FIELD_NAME)
    confirmations = confirmations if isinstance(confirmations, Mapping) else {}
    confirmation_fields = types.Object()
    confirm = confirmation_fields.bool(
        selected.key if selected else "_unselected",
        label="Confirm replacement",
        default=confirmations.get(selected.key) is True if selected else False,
        view=types.CheckboxView(),
        description=f"Replace '{selected.name}' ({selected.key}) with the current draft."
        if selected
        else "Select a pipeline to replace first.",
    )
    inputs.define_property(SAVE_PRESET_CONFIRM_FIELD_NAME, confirmation_fields, view=types.ObjectView())
    if editor_action(params) == "save":
        try:
            preset_update_target(params, store)
        except Exception as error:
            prop = confirm if selected else target
            prop.invalid = True
            prop.error_message = str(error)
